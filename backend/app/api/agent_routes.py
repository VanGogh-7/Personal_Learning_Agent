import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.db.session import get_db_session, get_session_factory
from app.embeddings.providers import EmbeddingProviderError
from app.graphs.chat_rag_graph import (
    ChatRAGGraphError,
    ChatRAGValidationError,
    run_chat_rag_graph,
)
from app.graphs.schemas import AgentChatRequest, AgentChatResponse
from app.llm.providers import LLMConfigurationError, LLMProviderError
from app.core.config import get_settings
from app.observability.latency import (
    AgentLatencyTrace,
    latency_trace_context,
    measure_latency_sync,
)
from app.rag.retrieval import LibraryItemRagError
from app.streaming.service import (
    DeferredTaskCollector,
    active_agent_runs,
    prepare_streaming_run,
    run_deferred_stream_tasks,
    stream_agent_sse_with_run_lock,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def agent_chat_endpoint(
    request: AgentChatRequest,
    background_tasks: BackgroundTasks | None = None,
    *,
    request_id: str | None = None,
) -> AgentChatResponse:
    trace = AgentLatencyTrace(request_id=request_id or str(uuid.uuid4()))
    error: BaseException | None = None
    try:
        with latency_trace_context(trace):
            response = _execute_agent_request(request, background_tasks)
            with measure_latency_sync("response_serialization", trace):
                response.model_dump_json(exclude={"debug"})
        trace.finish()
        settings = get_settings()
        if should_include_debug_timings(settings):
            response.debug = {
                "request_id": trace.request_id,
                "timings_ms": dict(trace.timings_ms),
            }
        return response
    except HTTPException as exc:
        error = exc
        raise
    except ChatRAGValidationError as exc:
        error = exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LibraryItemRagError as exc:
        error = exc
        detail = str(exc)
        status_code = 404 if detail == "Library item not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except ChatRAGGraphError as exc:
        error = exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        error = exc
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    except (EmbeddingProviderError, LLMConfigurationError, LLMProviderError) as exc:
        error = exc
        logger.warning(
            json.dumps(
                {
                    "event": "agent_provider_error",
                    "request_id": trace.request_id,
                    "provider": _provider_name(exc),
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        error = exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if get_settings().agent_latency_logging_enabled:
            trace.log_summary(error=error)


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat_http_endpoint(
    request: AgentChatRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
) -> AgentChatResponse:
    conversation_id = request.conversation_id
    if conversation_id and not active_agent_runs.acquire(conversation_id):
        raise HTTPException(
            status_code=409,
            detail="This conversation already has an active Agent run",
        )
    try:
        return agent_chat_endpoint(
            request,
            background_tasks,
            request_id=raw_request.state.request_id,
        )
    finally:
        if conversation_id:
            active_agent_runs.release(conversation_id)


@router.post("/chat/stream")
async def agent_chat_stream_endpoint(
    request: AgentChatRequest,
    raw_request: Request,
) -> StreamingResponse:
    settings = get_settings()
    if not settings.agent_streaming_enabled:
        raise HTTPException(status_code=409, detail="Agent streaming is disabled")
    session_factory = get_session_factory()
    try:
        run = await run_in_threadpool(
            prepare_streaming_run,
            request,
            request_id=raw_request.state.request_id,
            session_factory=session_factory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    conversation_id = str(run.identity.conversation_id)
    if not active_agent_runs.acquire(conversation_id):
        raise HTTPException(
            status_code=409,
            detail="This conversation already has an active Agent run",
        )
    deferred_tasks = DeferredTaskCollector()
    return StreamingResponse(
        stream_agent_sse_with_run_lock(
            run,
            disconnect_checker=raw_request.is_disconnected,
            deferred_tasks=deferred_tasks,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(run_deferred_stream_tasks, deferred_tasks),
    )


def _execute_agent_request(
    request: AgentChatRequest,
    background_tasks: BackgroundTasks | None = None,
) -> AgentChatResponse:
    db_session = get_db_session()
    session_bind = db_session.get_bind()

    def create_background_session() -> Session:
        return Session(bind=session_bind, expire_on_commit=False)

    try:
        response = run_chat_rag_graph(
            request,
            db_session,
            background_tasks=background_tasks,
            background_session_factory=create_background_session,
        )
        with measure_latency_sync("conversation_persist"):
            db_session.commit()
        return response
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def _provider_name(error: BaseException) -> str:
    if isinstance(error, EmbeddingProviderError):
        return "embedding"
    if isinstance(error, (LLMConfigurationError, LLMProviderError)):
        return "llm"
    return "unknown"


def should_include_debug_timings(settings: object) -> bool:
    app_env = str(getattr(settings, "app_env", "production")).strip().lower()
    enabled = bool(getattr(settings, "agent_debug_timings_in_response", False))
    return app_env != "production" and enabled
