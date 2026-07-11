"""Benchmark PLA Agent latency with deterministic providers by default.

Pass ``--real-providers`` explicitly to use provider configuration from the
environment. Real benchmarks consume API quota.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.vector_search import search_similar_chunks_for_documents
from app.embeddings.mock import MockEmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.graphs.chat_rag_graph import run_chat_rag_graph
from app.graphs.schemas import AgentChatRequest
from app.llm.providers import get_llm_provider
from app.memory.checkpointer import checkpointer_manager
from app.memory.conversations import resolve_conversation
from app.memory.retrieval import retrieve_memories
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from app.models.conversation import Conversation
from app.observability.latency import AgentLatencyTrace, latency_trace_context

SHORT_PROMPT = "Explain what a Banach space is in one sentence."
FULL_PROMPT = "\n".join(
    [
        "Explain complete metric spaces using the supplied learning context.",
        "Keep the answer grounded and concise.",
        *(f"Context item {index}: completeness controls Cauchy sequences." for index in range(80)),
    ]
)


@dataclass
class ScenarioResult:
    values_ms: list[float] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    stage_values_ms: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class BenchmarkFixture:
    session_factory: sessionmaker
    library_item_id: uuid.UUID
    document_id: uuid.UUID
    conversation_id: uuid.UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        conversation_id: uuid.UUID | None = None,
        library_item_id: uuid.UUID | None = None,
    ) -> "BenchmarkFixture":
        temp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        temp.close()
        engine = create_engine(f"sqlite+pysqlite:///{temp.name}", future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        provider = MockEmbeddingProvider()
        with factory() as session:
            item = LibraryItem(
                id=library_item_id or uuid.uuid4(),
                title="Latency Benchmark Book",
                status="indexed",
            )
            session.add(item)
            if conversation_id is not None:
                session.add(
                    Conversation(
                        id=conversation_id,
                        thread_id=f"benchmark-{conversation_id}",
                        namespace="benchmark_user",
                    )
                )
            session.flush()
            document = Document(
                title="Latency Benchmark Document",
                file_path=str(Path(temp.name).with_suffix(".pdf")),
                file_type="pdf",
                library_item_id=item.id,
            )
            session.add(document)
            session.flush()
            for index in range(12):
                content = (
                    f"Benchmark evidence {index}: a Banach space is a complete "
                    "normed vector space and Cauchy sequences converge."
                )
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=content,
                        char_start=index * 120,
                        char_end=index * 120 + len(content),
                        section_type="body",
                        embedding=provider.embed_text(content),
                    )
                )
            session.commit()
            return cls(factory, item.id, document.id, conversation_id)


class DeferredTasks:
    def __init__(self) -> None:
        self.tasks: list[tuple[Callable[..., object], dict[str, object]]] = []

    def add_task(self, function: Callable[..., object], **kwargs: object) -> None:
        self.tasks.append((function, kwargs))


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one successful value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
    }


def configure_providers(real_providers: bool) -> None:
    if not real_providers:
        os.environ["LLM_PROVIDER"] = "deterministic"
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["WEB_RESEARCH_PROVIDER"] = "deterministic"
    os.environ["MEMORY_CHECKPOINTER_BACKEND"] = "memory"
    get_settings.cache_clear()
    checkpointer_manager.shutdown()


def timed(action: Callable[[], object]) -> tuple[float, object]:
    started_at = time.perf_counter()
    value = action()
    return (time.perf_counter() - started_at) * 1000, value


def build_scenarios(fixture: BenchmarkFixture) -> dict[str, Callable[[], object]]:
    llm = get_llm_provider()
    embedding = get_embedding_provider()

    def vector_search() -> object:
        query = embedding.embed_text(SHORT_PROMPT)
        with fixture.session_factory() as session:
            return search_similar_chunks_for_documents(
                session, query, [fixture.document_id], limit=5
            )

    def memory_retrieval() -> object:
        with fixture.session_factory() as session:
            identity = resolve_conversation(session)
            result = retrieve_memories(
                session,
                namespace=identity.namespace,
                query=SHORT_PROMPT,
                update_access=False,
            )
            session.rollback()
            return result

    def agent_request(question: str, *, selected: bool) -> object:
        with fixture.session_factory() as session:
            request = AgentChatRequest(
                message=question,
                conversation_id=(
                    str(fixture.conversation_id) if fixture.conversation_id else None
                ),
                selected_library_item_id=(
                    str(fixture.library_item_id) if selected else None
                ),
            )
            trace = AgentLatencyTrace()
            with latency_trace_context(trace):
                response = run_chat_rag_graph(
                    request, session, background_tasks=DeferredTasks()
                )
            session.rollback()
            if not response.answer:
                raise RuntimeError("Agent benchmark returned an empty answer")
            return trace

    local_question = "What does this book say about complete normed spaces?"
    web_question = "What are the latest API updates about complete normed spaces?"
    both_question = "Explain Banach spaces using my book if relevant."
    return {
        "direct_llm_short_prompt": lambda: llm.generate(SHORT_PROMPT),
        "direct_llm_full_prompt": lambda: llm.generate(FULL_PROMPT),
        "embedding_only": lambda: embedding.embed_text(SHORT_PROMPT),
        "vector_search_only": vector_search,
        "local_only": lambda: agent_request(local_question, selected=True),
        "web_only": lambda: agent_request(web_question, selected=False),
        "both": lambda: agent_request(both_question, selected=True),
        "memory_retrieval_only": memory_retrieval,
        "complete_agent_request": lambda: agent_request(both_question, selected=True),
    }


def run_benchmark(
    scenarios: dict[str, Callable[[], object]], *, runs: int, warmups: int
) -> dict[str, ScenarioResult]:
    results: dict[str, ScenarioResult] = {}
    for name, action in scenarios.items():
        print(f"Running {name}...", flush=True)
        result = ScenarioResult()
        for _ in range(warmups):
            try:
                action()
            except Exception:
                break
        for _ in range(runs):
            try:
                elapsed_ms, value = timed(action)
                result.values_ms.append(elapsed_ms)
                if isinstance(value, AgentLatencyTrace):
                    for stage, stage_ms in value.timings_ms.items():
                        result.stage_values_ms.setdefault(stage, []).append(stage_ms)
            except Exception as exc:
                result.failures.append(type(exc).__name__)
        results[name] = result
    return results


def print_results(results: dict[str, ScenarioResult]) -> None:
    print(
        f"{'Stage':31} {'count':>5} {'min':>9} {'max':>9} "
        f"{'mean':>9} {'p50':>9} {'p90':>9} {'p95':>9} {'failed':>7}"
    )
    print("-" * 108)
    for name, result in results.items():
        if not result.values_ms:
            print(f"{name:31} {0:5d} {'-':>65} {len(result.failures):7d}")
            continue
        stats = summarize(result.values_ms)
        print(
            f"{name:31} {stats['count']:5d} {stats['min']:9.2f} "
            f"{stats['max']:9.2f} {stats['mean']:9.2f} {stats['p50']:9.2f} "
            f"{stats['p90']:9.2f} {stats['p95']:9.2f} {len(result.failures):7d}"
        )
        for stage in (
            "router_total",
            "query_embedding",
            "document_vector_search",
            "local_agent_total",
            "web_agent_total",
            "synthesis_ttft",
            "synthesis_generation",
            "synthesis_total",
            "conversation_persist",
            "checkpoint_persist",
        ):
            values = result.stage_values_ms.get(stage)
            if values:
                print(
                    f"  {name}.{stage:29} {'':5} {'':9} {'':9} {'':9} "
                    f"{percentile(values, 0.50):9.2f} {'':9} "
                    f"{percentile(values, 0.95):9.2f} {'':7}"
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--conversation-id")
    parser.add_argument("--library-item-id")
    parser.add_argument(
        "--scenario",
        action="append",
        help="Run only this scenario. May be supplied more than once.",
    )
    parser.add_argument(
        "--real-providers",
        action="store_true",
        help="Use configured providers. This consumes API quota.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs < 1 or args.warmups < 0:
        raise SystemExit("--runs must be positive and --warmups must be non-negative")
    if args.real_providers:
        print("WARNING: real provider benchmark enabled; API quota will be consumed.")
    else:
        print("Using deterministic/mock providers; no external API calls will be made.")
    configure_providers(args.real_providers)
    try:
        conversation_id = (
            uuid.UUID(args.conversation_id) if args.conversation_id else None
        )
        library_item_id = (
            uuid.UUID(args.library_item_id) if args.library_item_id else None
        )
    except ValueError as exc:
        raise SystemExit(f"Invalid benchmark UUID: {exc}") from exc
    fixture = BenchmarkFixture.create(
        conversation_id=conversation_id,
        library_item_id=library_item_id,
    )
    scenarios = build_scenarios(fixture)
    if args.scenario:
        unknown = sorted(set(args.scenario) - set(scenarios))
        if unknown:
            raise SystemExit(f"Unknown scenarios: {', '.join(unknown)}")
        scenarios = {name: scenarios[name] for name in args.scenario}
    results = run_benchmark(scenarios, runs=args.runs, warmups=args.warmups)
    print_results(results)
    checkpointer_manager.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
