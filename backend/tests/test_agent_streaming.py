import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import app.api.agent_routes as agent_routes_module
import app.graphs.chat_rag_graph as graph_module
from app.agents.web_research import WebResearchResult, WebSourceResult
from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.graphs.schemas import AgentChatRequest
from app.llm.providers import (
    LLMProviderError,
    LLMStreamChunk,
    OpenAICompatibleLLMProvider,
)
from app.models.conversation import Conversation
from app.models.conversation_turn import ConversationTurn
from app.mcp.client import mcp_client_manager
from app.streaming.events import (
    AgentStreamEventFactory,
    RunStartedEvent,
    StatusEvent,
    encode_sse_event,
)
from app.streaming.service import (
    ActiveAgentRunRegistry,
    DeferredTaskCollector,
    _finish_persistence_producer,
    _public_event_from_custom,
    active_agent_runs,
    compensate_stream_persistence,
    prepare_streaming_run,
    stream_agent_sse,
    stream_agent_sse_with_run_lock,
)


@pytest.fixture
def stream_session_factory(tmp_path, monkeypatch) -> sessionmaker:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'stream.sqlite3'}", future=True
    )
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


async def collect_events(
    request: AgentChatRequest, session_factory: sessionmaker
) -> list[dict]:
    run = prepare_streaming_run(
        request,
        request_id=str(uuid.uuid4()),
        session_factory=session_factory,
    )
    chunks = [
        chunk
        async for chunk in stream_agent_sse(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        if not chunk.startswith(b":")
    ]
    return [_decode_event(chunk) for chunk in chunks]


def _decode_event(chunk: bytes) -> dict:
    lines = chunk.decode("utf-8").strip().splitlines()
    assert lines[0].startswith("event: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload["type"] == lines[0].removeprefix("event: ")
    return payload


def test_sse_encoder_uses_single_json_line_and_monotonic_sequence() -> None:
    factory = AgentStreamEventFactory(
        request_id="request-1", conversation_id="conversation-1", run_id="run-1"
    )
    first = factory.create(RunStartedEvent, ui_flush_interval_ms=50)
    second = factory.create(
        StatusEvent, stage="loading_context", message="Loading conversation\ncontext"
    )
    encoded = encode_sse_event(second)
    assert encoded.endswith(b"\n\n")
    assert encoded.startswith(b"event: status\ndata: {")
    assert "Loading conversation" in encoded.decode("utf-8")
    assert "\\n" in encoded.decode("utf-8")
    assert first.sequence == 1
    assert second.sequence == 2
    assert b"prompt" not in encoded


def test_public_mapper_filters_non_synthesis_tokens_and_internal_payloads() -> None:
    factory = AgentStreamEventFactory(
        request_id="request-1", conversation_id="conversation-1", run_id="run-1"
    )
    assert (
        _public_event_from_custom(
            factory, {"kind": "router_token", "delta": "private reasoning"}
        )
        is None
    )
    assert (
        _public_event_from_custom(
            factory, {"kind": "tool_payload", "prompt": "sensitive prompt"}
        )
        is None
    )


def test_active_run_registry_locks_only_the_same_conversation() -> None:
    registry = ActiveAgentRunRegistry()
    assert registry.acquire("conversation-a") is True
    assert registry.acquire("conversation-a") is False
    assert registry.acquire("conversation-b") is True
    registry.release("conversation-a")
    assert registry.acquire("conversation-a") is True


@pytest.mark.anyio
async def test_persistence_completion_drains_bounded_queue() -> None:
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue(maxsize=1)
    await queue.put(("custom", {"kind": "status", "stage": "persisting"}))

    async def finish_graph() -> None:
        await queue.put(("complete", {}))

    producer = asyncio.create_task(finish_graph())
    await asyncio.wait_for(_finish_persistence_producer(producer, queue), timeout=1)

    assert producer.done()
    assert producer.cancelled() is False


def test_compensation_failure_emits_high_priority_structured_log(caplog) -> None:
    class FailingSession:
        def commit(self):
            raise SQLAlchemyError("secret-database-detail")

        def rollback(self):
            return None

        def close(self):
            return None

    result = compensate_stream_persistence(
        lambda: FailingSession(),
        {"request_id": "request-safe"},
    )
    assert result is False
    record = next(
        record for record in caplog.records if "compensation_failed" in record.message
    )
    payload = json.loads(record.message)
    assert record.levelname == "CRITICAL"
    assert payload["request_id"] == "request-safe"
    assert "secret-database-detail" not in record.message


@pytest.mark.anyio
async def test_async_provider_normalizes_deltas_finish_reason_and_usage() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"闭图像"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"定理"},"finish_reason":"stop"}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":2}}',
            "data: [DONE]",
            "",
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    provider = OpenAICompatibleLLMProvider(
        api_key="test",
        base_url="https://example.test",
        model="model",
        async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    chunks = [chunk async for chunk in provider.stream_chat_completion("prompt")]
    assert "".join(chunk.delta for chunk in chunks) == "闭图像定理"
    assert [chunk.finish_reason for chunk in chunks if chunk.finish_reason] == ["stop"]
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.completion_tokens == 2


@pytest.mark.anyio
async def test_async_provider_timeout_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    provider = OpenAICompatibleLLMProvider(
        api_key="test",
        base_url="https://example.test",
        model="model",
        async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LLMProviderError, match="streaming request failed"):
        async for _ in provider.stream_chat_completion("prompt"):
            pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "required_stage", "forbidden_stage"),
    [
        ("What does this book say?", "retrieving_local", "searching_web"),
        ("What are the latest API updates?", "searching_web", "retrieving_local"),
    ],
)
async def test_stream_route_activity_is_real_and_route_specific(
    stream_session_factory, message, required_stage, forbidden_stage
) -> None:
    events = await collect_events(
        AgentChatRequest(message=message), stream_session_factory
    )
    assert events[0]["type"] == "run_started"
    assert events[-1]["type"] == "done"
    stages = [event.get("stage") for event in events if event["type"] == "status"]
    assert required_stage in stages
    assert forbidden_stage not in stages
    assert "synthesizing" in stages
    assert "streaming" in stages
    assert any(event["type"] == "token" for event in events)
    assert [event["type"] for event in events][-3:] == ["citations", "final", "done"]
    sequences = [event["sequence"] for event in events]
    assert sequences == sorted(sequences)


@pytest.mark.anyio
async def test_both_stream_has_parallel_branch_activity(stream_session_factory) -> None:
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    stages = [event.get("stage") for event in events if event["type"] == "status"]
    assert "retrieving_local" in stages
    assert "searching_web" in stages


@pytest.mark.anyio
async def test_adaptive_activity_follows_real_graph_order(
    stream_session_factory,
) -> None:
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    stages = [event["stage"] for event in events if event["type"] == "status"]
    ordered = [
        "understanding_query",
        "planning_research",
        "evaluating_sources",
        "organizing_answer",
        "synthesizing",
        "verifying_citations",
        "persisting",
    ]
    assert [stages.index(stage) for stage in ordered] == sorted(
        stages.index(stage) for stage in ordered
    )
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_mcp_activity_is_public_but_tool_details_are_not(
    monkeypatch, stream_session_factory
) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()

    async def fake_web_research(question, *, gateway, activity):
        activity("searching_web", "Searching the web")
        return WebResearchResult(
            summary="Web evidence [W1].",
            sources=[
                WebSourceResult(
                    source_id="W1",
                    title="Web source",
                    url="https://example.test/web",
                    excerpt="Evidence",
                )
            ],
        )

    async def fake_academic_research(question, *, gateway, activity):
        activity("searching_academic", "Searching academic sources")
        return WebResearchResult(
            summary="Academic evidence [W1].",
            sources=[
                WebSourceResult(
                    source_id="W1",
                    title="Paper",
                    url="https://example.test/paper",
                    excerpt="Evidence",
                    provider="academic",
                    source_type="academic",
                )
            ],
        )

    monkeypatch.setattr(graph_module, "run_mcp_web_research", fake_web_research)
    monkeypatch.setattr(
        graph_module, "run_mcp_academic_research", fake_academic_research
    )
    events = await collect_events(
        AgentChatRequest(message="Find the latest research paper"),
        stream_session_factory,
    )
    stages = [event.get("stage") for event in events if event["type"] == "status"]
    assert "planning_research" in stages
    assert "searching_academic" in stages
    assert "evaluating_sources" in stages
    serialized = json.dumps(events)
    assert "search_arxiv" not in serialized
    assert "academic_client" not in serialized
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_local_only_never_calls_mcp(monkeypatch, stream_session_factory) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()

    async def forbidden(*args, **kwargs):
        raise AssertionError("local_only must not call MCP")

    monkeypatch.setattr(graph_module, "run_mcp_web_research", forbidden)
    monkeypatch.setattr(graph_module, "run_mcp_academic_research", forbidden)
    events = await collect_events(
        AgentChatRequest(message="What does this book say?"), stream_session_factory
    )
    assert events[-1]["type"] == "done"
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_legacy_json_web_node_reuses_lifespan_mcp_loop(monkeypatch) -> None:
    monkeypatch.setenv("MCP_ENABLED", "true")
    get_settings.cache_clear()

    async def fake_research(question, *, gateway):
        return WebResearchResult(
            summary="Web evidence [W1].",
            sources=[
                WebSourceResult(
                    source_id="W1",
                    title="Source",
                    url="https://example.test/source",
                    excerpt="Evidence",
                )
            ],
        )

    monkeypatch.setattr(graph_module, "run_mcp_web_research", fake_research)
    await mcp_client_manager.startup()
    try:
        result = await asyncio.to_thread(
            graph_module.web_research_agent_node,
            {"route": "web_only", "question": "What is current?"},
        )
    finally:
        await mcp_client_manager.shutdown()
        get_settings.cache_clear()
    assert result["web_sources"][0]["source_id"] == "W1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected_route"),
    [
        ("What does this book say?", "local_only"),
        ("What are the latest API updates?", "web_only"),
        ("Explain completeness", "both"),
    ],
)
async def test_stream_trace_counts_only_final_synthesis_llm_call(
    stream_session_factory, message, expected_route
) -> None:
    run = prepare_streaming_run(
        AgentChatRequest(message=message),
        request_id=str(uuid.uuid4()),
        session_factory=stream_session_factory,
    )
    events = [
        _decode_event(chunk)
        async for chunk in stream_agent_sse(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        if not chunk.startswith(b":")
    ]
    assert events[-1]["type"] == "done"
    assert run.trace.route == expected_route
    assert run.trace.counters["llm_call_count"] == 1
    assert run.trace.counters["embedding_call_count"] == 1
    assert run.trace.counters["stream_completed"] is True
    assert run.trace.counters["token_event_count"] > 0


@pytest.mark.anyio
async def test_both_stream_keeps_local_and_web_branches_parallel(
    monkeypatch, stream_session_factory
) -> None:
    def slow_local(*args, **kwargs):
        time.sleep(0.30)
        return []

    original_web = graph_module.run_web_research_agent_service

    def measured_web(question):
        time.sleep(0.50)
        return original_web(question)

    monkeypatch.setattr(graph_module, "retrieve_relevant_chunks", slow_local)
    monkeypatch.setattr(graph_module, "run_web_research_agent_service", measured_web)
    started_at = time.perf_counter()
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    elapsed = time.perf_counter() - started_at
    assert events[-1]["type"] == "done"
    assert 0.48 <= elapsed < 0.72


@pytest.mark.anyio
async def test_success_persists_one_complete_turn_after_tokens(
    stream_session_factory,
) -> None:
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    final = next(event for event in events if event["type"] == "final")
    citations = next(event for event in events if event["type"] == "citations")
    streamed = "".join(event["delta"] for event in events if event["type"] == "token")
    assert final["response"]["answer"] == streamed
    assert citations["citations"] == final["response"]["citations"]
    assert citations["web_sources"] == final["response"]["web_sources"]
    with stream_session_factory() as session:
        turns = list(session.execute(select(ConversationTurn)).scalars())
        assert len(turns) == 1
        assert turns[0].answer == streamed
        assert turns[0].metadata_json["citation_refs"] == []
        assert turns[0].metadata_json["citations"] == []
        assert turns[0].metadata_json["citations"] == final["response"]["citations"]
        assert turns[0].metadata_json["web_sources"] == final["response"]["web_sources"]
        assert (
            session.execute(select(func.count()).select_from(Conversation)).scalar_one()
            == 1
        )


@pytest.mark.anyio
async def test_streaming_reuses_conversation_context_and_matches_sync_semantics(
    stream_session_factory,
) -> None:
    first_events = await collect_events(
        AgentChatRequest(message="my name is Van."), stream_session_factory
    )
    first_final = next(event for event in first_events if event["type"] == "final")
    conversation_id = first_final["response"]["conversation_id"]
    second_events = await collect_events(
        AgentChatRequest(message="what is my name?", conversation_id=conversation_id),
        stream_session_factory,
    )
    second_final = next(event for event in second_events if event["type"] == "final")
    streamed = "".join(
        event["delta"] for event in second_events if event["type"] == "token"
    )

    assert "Van" in second_final["response"]["answer"]
    assert second_final["response"]["answer"] == streamed
    assert second_final["response"]["memory"]["used_recent_turns"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected_fragment"),
    [("Hello", "Hello"), ("你好", "您好")],
)
async def test_streaming_answer_language_follows_current_message(
    stream_session_factory, message, expected_fragment
) -> None:
    events = await collect_events(
        AgentChatRequest(message=message), stream_session_factory
    )
    final = next(event for event in events if event["type"] == "final")
    assert expected_fragment in final["response"]["answer"]


@pytest.mark.anyio
async def test_provider_failure_after_partial_token_does_not_persist(
    monkeypatch, stream_session_factory
) -> None:
    class FailingProvider:
        async def stream_chat_completion(
            self, prompt: str
        ) -> AsyncIterator[LLMStreamChunk]:
            yield LLMStreamChunk(delta="partial")
            raise LLMProviderError("provider disconnected")

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: FailingProvider())
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    assert any(event["type"] == "token" for event in events)
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "done" for event in events)
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(select(func.count()).select_from(Conversation)).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_cancelled_consumer_keeps_partial_text_and_does_not_persist(
    monkeypatch, stream_session_factory
) -> None:
    gate = asyncio.Event()
    provider_closed = asyncio.Event()

    class SlowProvider:
        async def stream_chat_completion(
            self, prompt: str
        ) -> AsyncIterator[LLMStreamChunk]:
            try:
                yield LLMStreamChunk(delta="partial")
                await gate.wait()
                yield LLMStreamChunk(delta="never", finish_reason="stop")
            finally:
                provider_closed.set()

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: SlowProvider())
    run = prepare_streaming_run(
        AgentChatRequest(message="Explain completeness"),
        request_id=str(uuid.uuid4()),
        session_factory=stream_session_factory,
    )
    deferred_tasks = DeferredTaskCollector()
    generator = stream_agent_sse(
        run,
        disconnect_checker=never_disconnected,
        deferred_tasks=deferred_tasks,
    )
    seen_token = False
    async for chunk in generator:
        if chunk.startswith(b":"):
            continue
        event = _decode_event(chunk)
        if event["type"] == "token":
            seen_token = True
            break
    await generator.aclose()
    assert seen_token is True
    await asyncio.wait_for(provider_closed.wait(), timeout=1)
    assert deferred_tasks.tasks == []
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(select(func.count()).select_from(Conversation)).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_client_disconnect_cancels_active_provider_stream(
    monkeypatch, stream_session_factory
) -> None:
    provider_started = asyncio.Event()
    provider_closed = asyncio.Event()
    gate = asyncio.Event()

    class WaitingProvider:
        async def stream_chat_completion(
            self, prompt: str
        ) -> AsyncIterator[LLMStreamChunk]:
            provider_started.set()
            try:
                await gate.wait()
                yield LLMStreamChunk(delta="never", finish_reason="stop")
            finally:
                provider_closed.set()

    async def disconnected() -> bool:
        return provider_started.is_set()

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: WaitingProvider())
    run = prepare_streaming_run(
        AgentChatRequest(message="Explain completeness"),
        request_id=str(uuid.uuid4()),
        session_factory=stream_session_factory,
    )
    events = [
        _decode_event(chunk)
        async for chunk in stream_agent_sse(
            run,
            disconnect_checker=disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        if not chunk.startswith(b":")
    ]
    assert events[-1]["type"] == "cancelled"
    assert not any(event["type"] == "done" for event in events)
    assert run.trace.counters["client_cancelled"] is True
    await asyncio.wait_for(provider_closed.wait(), timeout=1)
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_persistence_failure_emits_error_without_done(
    monkeypatch, stream_session_factory
) -> None:
    def fail_persistence(*args, **kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(graph_module, "ensure_conversation", fail_persistence)
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    assert any(event["type"] == "token" for event in events)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "persistence_failed"
    assert not any(event["type"] == "done" for event in events)
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_citation_persistence_failure_does_not_complete(
    monkeypatch, stream_session_factory
) -> None:
    def fail_turn(*args, **kwargs):
        raise SQLAlchemyError("citation metadata persistence failed")

    monkeypatch.setattr(graph_module, "save_turn", fail_turn)
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "done" for event in events)
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_checkpoint_failure_compensates_committed_turn(
    monkeypatch, stream_session_factory, caplog
) -> None:
    class FailingSaver(InMemorySaver):
        async def aput(self, *args, **kwargs):
            raise RuntimeError("checkpoint failure")

    monkeypatch.setattr(
        "app.streaming.service.checkpointer_manager.get", lambda: FailingSaver()
    )
    events = await collect_events(
        AgentChatRequest(message="Explain completeness"), stream_session_factory
    )
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "done" for event in events)
    assert any(
        "checkpoint_persist_failed" in record.message for record in caplog.records
    )
    with stream_session_factory() as session:
        assert (
            session.execute(
                select(func.count()).select_from(ConversationTurn)
            ).scalar_one()
            == 0
        )
        assert (
            session.execute(select(func.count()).select_from(Conversation)).scalar_one()
            == 0
        )


@pytest.mark.anyio
async def test_run_lock_is_released_after_stream_exception(
    monkeypatch, stream_session_factory
) -> None:
    class FailingProvider:
        async def stream_chat_completion(self, prompt: str):
            raise LLMProviderError("failed")
            yield

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: FailingProvider())
    run = prepare_streaming_run(
        AgentChatRequest(message="Explain completeness"),
        request_id=str(uuid.uuid4()),
        session_factory=stream_session_factory,
    )
    conversation_id = str(run.identity.conversation_id)
    assert active_agent_runs.acquire(conversation_id)
    events = [
        _decode_event(chunk)
        async for chunk in stream_agent_sse_with_run_lock(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        if not chunk.startswith(b":")
    ]
    assert events[-1]["type"] == "error"
    assert active_agent_runs.acquire(conversation_id) is True
    active_agent_runs.release(conversation_id)


@pytest.mark.anyio
async def test_run_lock_is_released_after_consumer_cancellation(
    monkeypatch, stream_session_factory
) -> None:
    gate = asyncio.Event()

    class SlowProvider:
        async def stream_chat_completion(self, prompt: str):
            yield LLMStreamChunk(delta="partial")
            await gate.wait()

    monkeypatch.setattr(graph_module, "get_llm_provider", lambda: SlowProvider())
    run = prepare_streaming_run(
        AgentChatRequest(message="Explain completeness"),
        request_id=str(uuid.uuid4()),
        session_factory=stream_session_factory,
    )
    conversation_id = str(run.identity.conversation_id)
    assert active_agent_runs.acquire(conversation_id)
    generator = stream_agent_sse_with_run_lock(
        run,
        disconnect_checker=never_disconnected,
        deferred_tasks=DeferredTaskCollector(),
    )
    async for chunk in generator:
        if not chunk.startswith(b":") and _decode_event(chunk)["type"] == "token":
            break
    await generator.aclose()
    assert active_agent_runs.acquire(conversation_id) is True
    active_agent_runs.release(conversation_id)


def test_validation_error_has_correlated_request_id_without_request_body(
    caplog,
) -> None:
    secret_message = "private-user-message-do-not-log"
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat/stream",
            json={"message": secret_message, "selected_library_item_ids": "invalid"},
        )
    assert response.status_code == 422
    request_id = response.json()["request_id"]
    assert response.headers["X-Request-ID"] == request_id
    matching = [
        record.message for record in caplog.records if request_id in record.message
    ]
    assert matching
    assert secret_message not in "\n".join(matching)


def test_streaming_endpoint_returns_sse_headers_and_terminal_done(
    monkeypatch, stream_session_factory
) -> None:
    monkeypatch.setattr(
        agent_routes_module, "get_session_factory", lambda: stream_session_factory
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat/stream",
            json={"message": "What does this book say?"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-request-id"]
    assert response.text.startswith("event: run_started\n")
    assert "event: token\n" in response.text
    assert response.text.rstrip().split("\n\n")[-1].startswith("event: done\n")
    started = json.loads(response.text.splitlines()[1].removeprefix("data: "))
    assert active_agent_runs.acquire(started["conversation_id"]) is True
    active_agent_runs.release(started["conversation_id"])
