import asyncio
import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.graphs.chat_rag_graph as graph_module
from app.core.config import get_settings
from app.db.base import Base
from app.graphs.schemas import AgentChatRequest
from app.llm.providers import DeterministicLLMProvider, LLMStreamChunk
from app.models.conversation_turn import ConversationTurn
from app.streaming.service import (
    DeferredTaskCollector,
    active_agent_runs,
    prepare_streaming_run,
    stream_agent_sse_with_run_lock,
)

pytestmark = pytest.mark.soak


@pytest.fixture
def soak_session_factory(tmp_path, monkeypatch) -> sessionmaker:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'soak.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        graph_module, "retrieve_relevant_chunks", lambda *args, **kwargs: []
    )
    try:
        yield factory
    finally:
        engine.dispose()


async def never_disconnected() -> bool:
    return False


@pytest.mark.anyio
async def test_repeated_short_streams_leave_no_tasks_or_registry_entries(
    soak_session_factory,
) -> None:
    runs = min(50, get_settings().pla_sse_soak_runs)
    baseline_tasks = len(asyncio.all_tasks())
    baseline_runs = active_agent_runs.count()
    for _ in range(runs):
        run = prepare_streaming_run(
            AgentChatRequest(message="What does this book say?"),
            request_id=str(uuid.uuid4()),
            session_factory=soak_session_factory,
        )
        conversation_id = str(run.identity.conversation_id)
        assert active_agent_runs.acquire(conversation_id)
        chunks = [
            chunk
            async for chunk in stream_agent_sse_with_run_lock(
                run,
                disconnect_checker=never_disconnected,
                deferred_tasks=DeferredTaskCollector(),
            )
        ]
        assert chunks[-1].startswith(b"event: done")
    await asyncio.sleep(0)
    assert active_agent_runs.count() == baseline_runs
    assert len(asyncio.all_tasks()) <= baseline_tasks + 1
    with soak_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == runs
        )


@pytest.mark.anyio
async def test_repeated_cancel_then_success_cycles_release_every_run(
    monkeypatch, soak_session_factory
) -> None:
    baseline_runs = active_agent_runs.count()

    class SlowProvider:
        async def stream_chat_completion(self, prompt: str):
            yield LLMStreamChunk(delta="partial")
            await asyncio.Event().wait()

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: SlowProvider())
    for _ in range(5):
        run = prepare_streaming_run(
            AgentChatRequest(message="Explain completeness"),
            request_id=str(uuid.uuid4()),
            session_factory=soak_session_factory,
        )
        conversation_id = str(run.identity.conversation_id)
        assert active_agent_runs.acquire(conversation_id)
        generator = stream_agent_sse_with_run_lock(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        async for chunk in generator:
            if chunk.startswith(b"event: token"):
                break
        await generator.aclose()
        assert active_agent_runs.count() == baseline_runs

    monkeypatch.setattr(
        graph_module, "get_llm_provider", lambda: DeterministicLLMProvider()
    )
    run = prepare_streaming_run(
        AgentChatRequest(message="What does this book say?"),
        request_id=str(uuid.uuid4()),
        session_factory=soak_session_factory,
    )
    conversation_id = str(run.identity.conversation_id)
    assert active_agent_runs.acquire(conversation_id)
    chunks = [
        chunk
        async for chunk in stream_agent_sse_with_run_lock(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
    ]
    assert chunks[-1].startswith(b"event: done")
    assert active_agent_runs.count() == baseline_runs
