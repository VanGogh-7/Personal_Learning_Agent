"""Benchmark public Agent SSE milestones with mock providers by default.

Pass ``--real-providers`` explicitly to consume configured DeepSeek, Zhipu,
and Tavily quota. A warmup run is performed before measured runs.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.graphs.chat_rag_graph as graph_module
from app.core.config import get_settings
from app.graphs.schemas import AgentChatRequest
from app.llm.providers import LLMStreamChunk
from app.memory.checkpointer import checkpointer_manager
from app.providers.http_clients import provider_http_clients
from app.streaming.service import (
    DeferredTaskCollector,
    prepare_streaming_run,
    stream_agent_sse,
)
from scripts.benchmark_agent_latency import (
    BenchmarkFixture,
    configure_providers,
    percentile,
    summarize,
)


@dataclass
class StreamRunResult:
    metrics_ms: dict[str, float]
    stream_event_count: int
    token_event_count: int
    streamed_character_count: int
    counters: dict[str, int | float | str | None]


@dataclass
class StreamScenarioResult:
    metrics_ms: dict[str, list[float]] = field(default_factory=dict)
    event_counts: list[int] = field(default_factory=list)
    token_counts: list[int] = field(default_factory=list)
    character_counts: list[int] = field(default_factory=list)
    counter_values: dict[str, list[int | float]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)


async def never_disconnected() -> bool:
    return False


def decode_event(chunk: bytes) -> dict[str, object] | None:
    if chunk.startswith(b":"):
        return None
    lines = chunk.decode("utf-8").strip().splitlines()
    return json.loads(lines[1].removeprefix("data: "))


async def measure_stream(
    fixture: BenchmarkFixture,
    *,
    question: str,
    selected: bool,
) -> StreamRunResult:
    request = AgentChatRequest(
        message=question,
        selected_library_item_id=str(fixture.library_item_id) if selected else None,
    )
    run = prepare_streaming_run(
        request,
        request_id=str(uuid.uuid4()),
        session_factory=fixture.session_factory,
    )
    started_at = time.perf_counter()
    first_status_at: float | None = None
    first_token_at: float | None = None
    last_token_at: float | None = None
    persisting_at: float | None = None
    citations_at: float | None = None
    done_at: float | None = None
    event_count = 0
    token_count = 0
    streamed_character_count = 0
    citations_payload: dict[str, object] | None = None
    final_payload: dict[str, object] | None = None
    async for chunk in stream_agent_sse(
        run,
        disconnect_checker=never_disconnected,
        deferred_tasks=DeferredTaskCollector(),
    ):
        event = decode_event(chunk)
        if event is None:
            continue
        now = time.perf_counter()
        event_count += 1
        event_type = event["type"]
        if event_type == "status" and first_status_at is None:
            first_status_at = now
        if event_type == "status" and event.get("stage") == "persisting":
            persisting_at = now
        if event_type == "token":
            token_count += 1
            streamed_character_count += len(str(event.get("delta") or ""))
            first_token_at = first_token_at or now
            last_token_at = now
        if event_type == "error":
            raise RuntimeError(str(event.get("code")))
        if event_type == "citations":
            citations_at = now
            citations_payload = event
        if event_type == "final":
            final_payload = event
        if event_type == "done":
            done_at = now
    if not all(
        (
            first_status_at,
            first_token_at,
            last_token_at,
            persisting_at,
            citations_at,
            done_at,
        )
    ):
        raise RuntimeError("stream did not expose every required milestone")
    if citations_payload is None or final_payload is None:
        raise RuntimeError("stream did not finalize citations")
    response = final_payload.get("response")
    if not isinstance(response, dict):
        raise RuntimeError("stream final event has no response")
    if citations_payload.get("citations") != response.get("citations"):
        raise RuntimeError("local citations changed between citations and final")
    if citations_payload.get("web_sources") != response.get("web_sources"):
        raise RuntimeError("web sources changed between citations and final")
    return StreamRunResult(
        metrics_ms={
            "first_status": (first_status_at - started_at) * 1000,
            "first_token": (first_token_at - started_at) * 1000,
            "generation": (last_token_at - first_token_at) * 1000,
            "final_persist": (done_at - persisting_at) * 1000,
            "citations_ready": (citations_at - started_at) * 1000,
            "total": (done_at - started_at) * 1000,
        },
        stream_event_count=event_count,
        token_event_count=token_count,
        streamed_character_count=streamed_character_count,
        counters=dict(run.trace.counters),
    )


async def cancellation_latency(fixture: BenchmarkFixture) -> float:
    closed = asyncio.Event()
    gate = asyncio.Event()

    class CancellableProvider:
        async def stream_chat_completion(
            self, prompt: str
        ) -> AsyncIterator[LLMStreamChunk]:
            try:
                yield LLMStreamChunk(delta="partial")
                await gate.wait()
            finally:
                closed.set()

    original = graph_module.get_llm_provider
    graph_module.get_llm_provider = lambda: CancellableProvider()
    try:
        run = prepare_streaming_run(
            AgentChatRequest(message="What are the latest API updates?"),
            request_id=str(uuid.uuid4()),
            session_factory=fixture.session_factory,
        )
        generator = stream_agent_sse(
            run,
            disconnect_checker=never_disconnected,
            deferred_tasks=DeferredTaskCollector(),
        )
        async for chunk in generator:
            event = decode_event(chunk)
            if event and event["type"] == "token":
                started_at = time.perf_counter()
                await generator.aclose()
                await closed.wait()
                return (time.perf_counter() - started_at) * 1000
    finally:
        graph_module.get_llm_provider = original
    raise RuntimeError("cancellation benchmark received no token")


async def run_scenario(
    fixture: BenchmarkFixture,
    *,
    question: str,
    selected: bool,
    runs: int,
    warmups: int,
) -> StreamScenarioResult:
    result = StreamScenarioResult()
    for _ in range(warmups):
        try:
            await measure_stream(fixture, question=question, selected=selected)
        except Exception:
            pass
    for _ in range(runs):
        try:
            measured = await measure_stream(
                fixture, question=question, selected=selected
            )
            for metric, value in measured.metrics_ms.items():
                result.metrics_ms.setdefault(metric, []).append(value)
            result.event_counts.append(measured.stream_event_count)
            result.token_counts.append(measured.token_event_count)
            result.character_counts.append(measured.streamed_character_count)
            for counter in (
                "llm_call_count",
                "embedding_call_count",
                "web_search_call_count",
                "tavily_call_count",
            ):
                value = measured.counters.get(counter)
                if isinstance(value, (int, float)):
                    result.counter_values.setdefault(counter, []).append(value)
        except Exception as exc:
            result.failures.append(type(exc).__name__)
    return result


def print_results(results: dict[str, StreamScenarioResult]) -> None:
    print(f"{'Route / metric':31} {'count':>5} {'mean':>9} {'p50':>9} {'p95':>9}")
    print("-" * 69)
    for route, result in results.items():
        for metric, values in result.metrics_ms.items():
            stats = summarize(values)
            print(
                f"{route + '.' + metric:31} {stats['count']:5d} "
                f"{stats['mean']:9.2f} {stats['p50']:9.2f} {stats['p95']:9.2f}"
            )
        print(
            f"  events mean={sum(result.event_counts) / max(1, len(result.event_counts)):.1f}; "
            f"tokens mean={sum(result.token_counts) / max(1, len(result.token_counts)):.1f}; "
            f"characters mean={sum(result.character_counts) / max(1, len(result.character_counts)):.1f}; "
            f"failed={len(result.failures)}"
        )
        for counter, values in result.counter_values.items():
            print(f"  {counter} mean={sum(values) / len(values):.2f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--conversation-id")
    parser.add_argument("--library-item-id")
    parser.add_argument("--real-providers", action="store_true")
    return parser.parse_args()


async def _run_benchmark_body(
    args: argparse.Namespace, fixture: BenchmarkFixture
) -> int:
    scenarios = {
        "local_only": ("What does this book say about Banach spaces?", True),
        "web_only": ("What are the latest API updates about Banach spaces?", False),
        "both": ("Explain Banach spaces using my book if relevant.", True),
    }
    results = {
        name: await run_scenario(
            fixture,
            question=question,
            selected=selected,
            runs=args.runs,
            warmups=args.warmups,
        )
        for name, (question, selected) in scenarios.items()
    }
    print_results(results)
    cancellation = [await cancellation_latency(fixture) for _ in range(args.runs)]
    print(
        "synthetic_cancellation_latency "
        f"p50={percentile(cancellation, 0.50):.2f}ms "
        f"p95={percentile(cancellation, 0.95):.2f}ms"
    )
    return 1 if any(result.failures for result in results.values()) else 0


async def run_benchmark(args: argparse.Namespace, fixture: BenchmarkFixture) -> int:
    try:
        return await _run_benchmark_body(args, fixture)
    finally:
        await provider_http_clients.aclose()


def main() -> int:
    args = parse_args()
    if args.runs < 1 or args.warmups < 0:
        raise SystemExit("--runs must be positive and --warmups must be non-negative")
    if args.real_providers and not get_settings().pla_real_provider_tests:
        raise SystemExit(
            "Real benchmarks are disabled. Set PLA_REAL_PROVIDER_TESTS=true "
            "before using --real-providers."
        )
    print(
        "WARNING: real Provider benchmark consumes API quota."
        if args.real_providers
        else "Using deterministic/mock providers; no external API calls will be made."
    )
    configure_providers(args.real_providers)
    try:
        fixture = BenchmarkFixture.create(
            conversation_id=(
                uuid.UUID(args.conversation_id) if args.conversation_id else None
            ),
            library_item_id=(
                uuid.UUID(args.library_item_id) if args.library_item_id else None
            ),
        )
    except ValueError as exc:
        raise SystemExit(f"Invalid benchmark UUID: {exc}") from exc
    try:
        return asyncio.run(run_benchmark(args, fixture))
    finally:
        checkpointer_manager.shutdown()
        provider_http_clients.close()


if __name__ == "__main__":
    raise SystemExit(main())
