from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from time import perf_counter
from threading import RLock
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _default_counters() -> dict[str, int | float | str | None]:
    return {
        "llm_call_count": 0,
        "embedding_call_count": 0,
        "selected_library_item_count": 0,
        "retrieved_chunk_count": 0,
        "retrieved_memory_count": 0,
        "web_result_count": 0,
        "web_search_call_count": 0,
        "tavily_call_count": 0,
        "prompt_input_tokens": None,
        "completion_tokens": None,
        "output_character_count": 0,
        "route": None,
        "streaming_enabled": False,
        "stream_event_count": 0,
        "token_event_count": 0,
        "streamed_character_count": 0,
        "client_cancelled": False,
        "stream_completed": False,
        "stream_failed": False,
    }


@dataclass
class AgentLatencyTrace:
    """Request-scoped latency measurements without prompt or response content."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str | None = None
    route: str | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int | float | str | None] = field(
        default_factory=_default_counters
    )
    _started_at: float = field(default_factory=perf_counter, repr=False)
    _stage_counts: dict[str, int] = field(default_factory=dict, repr=False)
    _query_embeddings: dict[tuple[str, int, str], list[float]] = field(
        default_factory=dict, repr=False
    )
    _logged: bool = field(default=False, repr=False)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def record(self, stage: str, elapsed_ms: float) -> None:
        with self._lock:
            normalized = stage.removesuffix("_ms")
            rounded = round(elapsed_ms, 2)
            self.timings_ms[normalized] = round(
                self.timings_ms.get(normalized, 0.0) + rounded, 2
            )
            count = self._stage_counts.get(normalized, 0) + 1
            self._stage_counts[normalized] = count
            if count > 1:
                self.counters[f"{normalized}_count"] = count

    def increment(self, counter: str, amount: int = 1) -> None:
        with self._lock:
            current = self.counters.get(counter)
            self.counters[counter] = int(current or 0) + amount

    def set_counter(self, counter: str, value: int | float | str | None) -> None:
        with self._lock:
            self.counters[counter] = value

    def finish(self) -> None:
        self.timings_ms["request_total"] = round(
            (perf_counter() - self._started_at) * 1000, 2
        )

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self._started_at) * 1000, 2)

    def summary(
        self, *, event: str, error: BaseException | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": event,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "route": self.route,
            **self.counters,
            "timings_ms": dict(self.timings_ms),
        }
        if error is not None:
            payload["error_type"] = type(error).__name__
        return payload

    def log_summary(self, *, error: BaseException | None = None) -> None:
        if self._logged:
            return
        self.finish()
        event = (
            "agent_request_failed" if error is not None else "agent_request_completed"
        )
        logger.info(
            json.dumps(
                self.summary(event=event, error=error),
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        self._logged = True

    def get_or_create_query_embedding(
        self,
        *,
        provider_name: str,
        dimension: int,
        text: str,
        create: Callable[[], list[float]],
    ) -> list[float]:
        normalized_text = " ".join(text.strip().split())
        key = (provider_name, dimension, normalized_text)
        with self._lock:
            cached = self._query_embeddings.get(key)
            if cached is not None:
                current = self.counters.get("query_embedding_cache_hit_count")
                self.counters["query_embedding_cache_hit_count"] = int(current or 0) + 1
                return cached
        started_at = perf_counter()
        try:
            embedding = create()
        finally:
            self.record("query_embedding", (perf_counter() - started_at) * 1000)
        with self._lock:
            current = self.counters.get("embedding_call_count")
            self.counters["embedding_call_count"] = int(current or 0) + 1
            self._query_embeddings[key] = embedding
        return embedding


_current_trace: ContextVar[AgentLatencyTrace | None] = ContextVar(
    "agent_latency_trace", default=None
)


def current_latency_trace() -> AgentLatencyTrace | None:
    return _current_trace.get()


@contextmanager
def latency_trace_context(trace: AgentLatencyTrace) -> Iterator[AgentLatencyTrace]:
    token: Token[AgentLatencyTrace | None] = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


@asynccontextmanager
async def measure_latency(
    stage: str, trace: AgentLatencyTrace | None = None
) -> AsyncIterator[None]:
    resolved = trace or current_latency_trace()
    started_at = perf_counter()
    try:
        yield
    finally:
        if resolved is not None:
            resolved.record(stage, (perf_counter() - started_at) * 1000)


@contextmanager
def measure_latency_sync(
    stage: str, trace: AgentLatencyTrace | None = None
) -> Iterator[None]:
    resolved = trace or current_latency_trace()
    started_at = perf_counter()
    try:
        yield
    finally:
        if resolved is not None:
            resolved.record(stage, (perf_counter() - started_at) * 1000)


def get_request_query_embedding(provider: Any, text: str) -> list[float]:
    trace = current_latency_trace()
    if trace is None:
        return provider.embed_text(text)
    return trace.get_or_create_query_embedding(
        provider_name=str(getattr(provider, "provider_name", type(provider).__name__)),
        dimension=int(provider.dimension),
        text=text,
        create=lambda: provider.embed_text(text),
    )
