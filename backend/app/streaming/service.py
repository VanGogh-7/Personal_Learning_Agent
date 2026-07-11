from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.providers import EmbeddingProviderError
from app.graphs.chat_rag_graph import (
    AgentGraphState,
    ChatRAGGraphError,
    build_initial_agent_state,
    build_streaming_chat_rag_graph,
)
from app.graphs.schemas import AgentChatRequest, AgentChatResponse
from app.llm.providers import LLMProviderError
from app.memory.checkpointer import checkpointer_manager
from app.memory.conversations import ConversationIdentity, resolve_conversation
from app.models.conversation import Conversation
from app.models.conversation_turn import ConversationTurn
from app.models.learning_event import LearningEvent
from app.observability.checkpointer import TimedCheckpointer
from app.observability.latency import (
    AgentLatencyTrace,
    latency_trace_context,
    measure_latency_sync,
)
from app.streaming.events import (
    AgentStreamEventBase,
    AgentStreamEventFactory,
    CancelledEvent,
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    FinalEvent,
    RetrievalCompletedEvent,
    RouteSelectedEvent,
    RunStartedEvent,
    StatusEvent,
    TokenEvent,
    WarningEvent,
    encode_sse_event,
    encode_sse_heartbeat,
)

logger = logging.getLogger(__name__)
DisconnectChecker = Callable[[], Awaitable[bool]]


class ActiveAgentRunRegistry:
    """Enforce one in-process stream per conversation without cross-chat blocking."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._conversation_ids: set[str] = set()

    def acquire(self, conversation_id: str) -> bool:
        with self._lock:
            if conversation_id in self._conversation_ids:
                return False
            self._conversation_ids.add(conversation_id)
            return True

    def release(self, conversation_id: str) -> None:
        with self._lock:
            self._conversation_ids.discard(conversation_id)

    def count(self) -> int:
        with self._lock:
            return len(self._conversation_ids)


active_agent_runs = ActiveAgentRunRegistry()


@dataclass
class DeferredTaskCollector:
    tasks: list[tuple[Callable[..., object], dict[str, object]]] = field(
        default_factory=list
    )

    def add_task(self, function: Callable[..., object], **kwargs: object) -> None:
        self.tasks.append((function, kwargs))

    def clear(self) -> None:
        self.tasks.clear()


@dataclass(frozen=True)
class AgentStreamingRun:
    request: AgentChatRequest
    identity: ConversationIdentity
    request_id: str
    run_id: str
    session_factory: Callable[[], Session]
    conversation_is_provisional: bool
    trace: AgentLatencyTrace


def prepare_streaming_run(
    request: AgentChatRequest,
    *,
    request_id: str,
    session_factory: Callable[[], Session],
) -> AgentStreamingRun:
    """Resolve an existing conversation or provision one without persisting it."""
    trace = AgentLatencyTrace(request_id=request_id)
    try:
        with latency_trace_context(trace):
            with measure_latency_sync("conversation_load"):
                identity, provisional = _resolve_streaming_identity(
                    request, session_factory
                )
    except Exception as exc:
        if get_settings().agent_latency_logging_enabled:
            trace.log_summary(error=exc)
        raise
    trace.conversation_id = str(identity.conversation_id)
    trace.set_counter("streaming_enabled", True)
    return AgentStreamingRun(
        request=request,
        identity=identity,
        request_id=request_id,
        run_id=str(uuid.uuid4()),
        session_factory=session_factory,
        conversation_is_provisional=provisional,
        trace=trace,
    )


def _resolve_streaming_identity(
    request: AgentChatRequest, session_factory: Callable[[], Session]
) -> tuple[ConversationIdentity, bool]:
    requested_id = (
        uuid.UUID(request.conversation_id) if request.conversation_id else None
    )
    if requested_id is None and not request.session_id:
        conversation_id = uuid.uuid4()
        return (
            ConversationIdentity(
                conversation_id=conversation_id,
                thread_id=str(uuid.uuid4()),
                session_id=str(conversation_id),
                namespace=get_settings().memory_default_namespace,
            ),
            True,
        )
    session = session_factory()
    try:
        identity = resolve_conversation(
            session,
            conversation_id=requested_id,
            legacy_session_id=request.session_id,
        )
        return identity, session.get(Conversation, identity.conversation_id) is None
    finally:
        session.rollback()
        session.close()


async def stream_agent_sse(
    run: AgentStreamingRun,
    *,
    disconnect_checker: DisconnectChecker,
    deferred_tasks: DeferredTaskCollector,
) -> AsyncIterator[bytes]:
    settings = get_settings()
    trace = run.trace
    factory = AgentStreamEventFactory(
        request_id=run.request_id,
        conversation_id=str(run.identity.conversation_id),
        run_id=run.run_id,
    )
    receipt: dict[str, Any] = {"request_id": run.request_id}
    # One-event backpressure keeps Provider production, client delivery, and
    # disconnect checks interleaved instead of buffering a whole answer.
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=1)
    successful = False
    terminal_error: BaseException | None = None
    producer: asyncio.Task[None] | None = None
    persistence_started = False
    first_token_elapsed: float | None = None
    last_token_elapsed: float | None = None
    try:
        with latency_trace_context(trace):
            trace.record("stream_open", trace.elapsed_ms())
            run_started = factory.create(
                RunStartedEvent,
                ui_flush_interval_ms=settings.agent_stream_ui_flush_interval_ms,
            )
            trace.record("first_event", trace.elapsed_ms())
            yield _encode_and_count(run_started, trace)

            graph = build_streaming_chat_rag_graph(
                session_factory=run.session_factory,
                deferred_tasks=deferred_tasks,
                persistence_receipt=receipt,
                checkpointer=TimedCheckpointer(checkpointer_manager.get()),
            )
            initial_state = build_initial_agent_state(run.request, run.identity)
            producer = asyncio.create_task(
                _produce_graph_events(
                    graph,
                    initial_state,
                    thread_id=run.identity.thread_id,
                    queue=queue,
                )
            )
            heartbeat_at = monotonic() + settings.agent_stream_heartbeat_seconds
            final_state: AgentGraphState | None = None
            while final_state is None:
                if await disconnect_checker():
                    trace.set_counter("client_cancelled", True)
                    terminal_error = RuntimeError("client_cancelled")
                    if persistence_started:
                        with suppress(asyncio.CancelledError, Exception):
                            await asyncio.shield(producer)
                    else:
                        producer.cancel()
                        with suppress(asyncio.CancelledError):
                            await producer
                    cancelled = factory.create(CancelledEvent)
                    yield _encode_and_count(cancelled, trace)
                    return
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    if monotonic() >= heartbeat_at:
                        yield encode_sse_heartbeat()
                        heartbeat_at = (
                            monotonic() + settings.agent_stream_heartbeat_seconds
                        )
                    continue
                if kind == "custom":
                    event = _public_event_from_custom(factory, payload)
                    if event is None:
                        continue
                    if (
                        isinstance(event, StatusEvent)
                        and "first_status" not in trace.timings_ms
                    ):
                        trace.record("first_status", trace.elapsed_ms())
                    if isinstance(event, StatusEvent) and event.stage == "persisting":
                        persistence_started = True
                    if isinstance(event, TokenEvent):
                        elapsed = trace.elapsed_ms()
                        first_token_elapsed = first_token_elapsed or elapsed
                        last_token_elapsed = elapsed
                        if "first_token" not in trace.timings_ms:
                            trace.record("first_token", elapsed)
                        trace.increment("token_event_count")
                        trace.increment("streamed_character_count", len(event.delta))
                    yield _encode_and_count(event, trace)
                elif kind == "complete":
                    final_state = payload
                elif kind == "error":
                    raise payload

            if await disconnect_checker():
                trace.set_counter("client_cancelled", True)
                terminal_error = RuntimeError("client_cancelled")
                return

            response_data = final_state.get("response")
            message_id = final_state.get("persisted_turn_id")
            if response_data is None or not message_id:
                raise ChatRAGGraphError(
                    "Streaming graph did not persist a final response"
                )
            response = AgentChatResponse.model_validate(response_data)
            for warning in response.warnings:
                yield _encode_and_count(
                    factory.create(WarningEvent, message=warning), trace
                )
            yield _encode_and_count(
                factory.create(
                    CitationsEvent,
                    citations=response.citations,
                    web_sources=response.web_sources,
                ),
                trace,
            )
            yield _encode_and_count(
                factory.create(
                    FinalEvent,
                    message_id=message_id,
                    response=response,
                ),
                trace,
            )
            if first_token_elapsed is not None and last_token_elapsed is not None:
                trace.record(
                    "stream_generation",
                    max(0.0, last_token_elapsed - first_token_elapsed),
                )
            trace.set_counter("stream_completed", True)
            trace.record("done_event", trace.elapsed_ms())
            successful = True
            yield _encode_and_count(factory.create(DoneEvent), trace)
    except asyncio.CancelledError as exc:
        terminal_error = exc
        trace.set_counter("client_cancelled", True)
        raise
    except GeneratorExit as exc:
        terminal_error = exc
        trace.set_counter("client_cancelled", True)
        raise
    except Exception as exc:
        terminal_error = exc
        trace.set_counter("stream_failed", True)
        logger.warning(
            "agent_stream_failed request_id=%s provider=%s error_type=%s "
            "streamed_character_count=%s",
            run.request_id,
            _provider_name_for_error(exc),
            type(exc).__name__,
            trace.counters.get("streamed_character_count", 0),
        )
        event = factory.create(
            ErrorEvent,
            code=_safe_error_code(exc),
            message=_safe_error_message(exc),
            recoverable=True,
            partial_output_preserved=bool(
                trace.counters.get("streamed_character_count", 0)
            ),
        )
        yield _encode_and_count(event, trace)
    finally:
        if producer is not None and not producer.done():
            if persistence_started:
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(producer)
            else:
                producer.cancel()
                with suppress(asyncio.CancelledError):
                    await producer
        if not successful and receipt:
            await asyncio.to_thread(
                compensate_stream_persistence, run.session_factory, receipt
            )
            deferred_tasks.clear()
        if settings.agent_latency_logging_enabled:
            trace.log_summary(error=None if successful else terminal_error)


async def stream_agent_sse_with_run_lock(
    run: AgentStreamingRun,
    *,
    disconnect_checker: DisconnectChecker,
    deferred_tasks: DeferredTaskCollector,
) -> AsyncIterator[bytes]:
    conversation_id = str(run.identity.conversation_id)
    generator = stream_agent_sse(
        run,
        disconnect_checker=disconnect_checker,
        deferred_tasks=deferred_tasks,
    )
    try:
        async for chunk in generator:
            yield chunk
    finally:
        await generator.aclose()
        active_agent_runs.release(conversation_id)


async def _produce_graph_events(
    graph: Any,
    initial_state: AgentGraphState,
    *,
    thread_id: str,
    queue: asyncio.Queue[tuple[str, Any]],
) -> None:
    final_state: AgentGraphState | None = None
    try:
        async for mode, payload in graph.astream(
            initial_state,
            {"configurable": {"thread_id": thread_id}},
            stream_mode=["custom", "values"],
            durability="exit",
        ):
            if mode == "custom":
                await queue.put(("custom", payload))
            elif mode == "values":
                final_state = payload
        if final_state is None:
            raise ChatRAGGraphError("Streaming graph returned no final state")
        await queue.put(("complete", final_state))
    except Exception as exc:
        await queue.put(("error", exc))


def _public_event_from_custom(
    factory: AgentStreamEventFactory, payload: object
) -> AgentStreamEventBase | None:
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "status":
        return factory.create(
            StatusEvent,
            stage=payload["stage"],
            message=payload["message"],
        )
    if kind == "route_selected":
        return factory.create(RouteSelectedEvent, route=payload["route"])
    if kind == "retrieval_completed":
        return factory.create(
            RetrievalCompletedEvent,
            source=payload["source"],
            result_count=payload["result_count"],
        )
    if kind == "synthesis_token":
        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            return factory.create(TokenEvent, delta=delta)
    return None


def _encode_and_count(event: AgentStreamEventBase, trace: AgentLatencyTrace) -> bytes:
    trace.increment("stream_event_count")
    return encode_sse_event(event)


def run_deferred_stream_tasks(collector: DeferredTaskCollector) -> None:
    for function, kwargs in collector.tasks:
        try:
            function(**kwargs)
        except Exception as exc:
            logger.warning(
                "agent_stream_background_task_failed error_type=%s",
                type(exc).__name__,
            )


def compensate_stream_persistence(
    session_factory: Callable[[], Session], receipt: dict[str, Any]
) -> bool:
    session = session_factory()
    try:
        event_id = receipt.get("persisted_learning_event_id")
        turn_id = receipt.get("persisted_turn_id")
        if event_id:
            event = session.get(LearningEvent, uuid.UUID(str(event_id)))
            if event is not None:
                session.delete(event)
        if turn_id:
            turn = session.get(ConversationTurn, uuid.UUID(str(turn_id)))
            if turn is not None:
                session.delete(turn)
        if receipt.get("conversation_created") and receipt.get("conversation_id"):
            conversation = session.get(
                Conversation, uuid.UUID(str(receipt["conversation_id"]))
            )
            if conversation is not None:
                session.delete(conversation)
        session.commit()
        return True
    except Exception as exc:
        session.rollback()
        logger.critical(
            json.dumps(
                {
                    "event": "agent_stream_compensation_failed",
                    "request_id": receipt.get("request_id"),
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        return False
    finally:
        session.close()


def _safe_error_code(error: BaseException) -> str:
    name = type(error).__name__
    if "Provider" in name or "LLM" in name:
        return "provider_stream_failed"
    if "SQL" in name or "Database" in name:
        return "persistence_failed"
    if "Validation" in name or isinstance(error, ValueError):
        return "invalid_request"
    return "agent_stream_failed"


def _provider_name_for_error(error: BaseException) -> str:
    settings = get_settings()
    if isinstance(error, LLMProviderError):
        return settings.llm_provider
    if isinstance(error, EmbeddingProviderError):
        return settings.embedding_provider
    return "agent"


def _safe_error_message(error: BaseException) -> str:
    code = _safe_error_code(error)
    if code == "provider_stream_failed":
        return "The answer stream was interrupted by the model provider."
    if code == "persistence_failed":
        return "The answer was generated but could not be saved."
    if code == "invalid_request":
        return "The Agent request is invalid."
    return "The Agent stream could not be completed."
