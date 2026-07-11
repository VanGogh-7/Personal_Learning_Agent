import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
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

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def agent_chat_endpoint(
    request: AgentChatRequest,
    background_tasks: BackgroundTasks | None = None,
) -> AgentChatResponse:
    trace = AgentLatencyTrace()
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
) -> AgentChatResponse:
    return agent_chat_endpoint(request, background_tasks)


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
