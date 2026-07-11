import json
import logging
import time
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.memory.consolidation import ConsolidationResult, consolidate_candidate
from app.memory.extraction import (
    ConservativeMemoryCandidateExtractor,
    MemoryCandidateExtractor,
)
from app.memory.summary import update_rolling_summary_if_needed
from app.observability.latency import measure_latency_sync
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from app.db.session import get_db_session

logger = logging.getLogger(__name__)


def extract_and_consolidate_turn(
    session: Session,
    *,
    conversation_id: uuid.UUID,
    namespace: str,
    source_turn_id: uuid.UUID,
    user_message: str,
    extractor: MemoryCandidateExtractor | None = None,
) -> list[ConsolidationResult]:
    started = time.perf_counter()
    resolved_extractor = extractor or ConservativeMemoryCandidateExtractor()
    with measure_latency_sync("memory_extraction"):
        candidates = resolved_extractor.extract(user_message)
    with measure_latency_sync("memory_consolidation"):
        results = [
            consolidate_candidate(
                session,
                namespace=namespace,
                candidate=candidate,
                source_turn_id=source_turn_id,
            )
            for candidate in candidates
        ]
    logger.info(
        "memory_extraction_complete conversation_id=%s memory_candidate_count=%d actions=%s latency_ms=%.2f",
        conversation_id,
        len(candidates),
        [result.action.value for result in results],
        (time.perf_counter() - started) * 1000,
    )
    return results


def maintain_conversation_summary(
    session: Session, *, conversation_id: uuid.UUID
) -> bool:
    result = update_rolling_summary_if_needed(session, conversation_id=conversation_id)
    logger.info(
        "memory_summary_complete conversation_id=%s summary_updated=%s source_turn_count=%d",
        conversation_id,
        result.updated,
        result.source_turn_count,
    )
    return result.updated


def run_post_response_memory_processing(
    *,
    request_id: str,
    conversation_id: uuid.UUID,
    namespace: str,
    source_turn_id: uuid.UUID,
    user_message: str,
    route: str,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Run non-critical memory writes after the HTTP response with a new session."""
    trace = AgentLatencyTrace(
        request_id=request_id,
        conversation_id=str(conversation_id),
        route=route,
    )
    error: BaseException | None = None
    session = (session_factory or get_db_session)()
    try:
        with latency_trace_context(trace):
            try:
                with session.begin_nested():
                    with measure_latency_sync("conversation_summary"):
                        maintain_conversation_summary(
                            session, conversation_id=conversation_id
                        )
            except Exception as exc:
                logger.warning(
                    "background_memory_summary_failed request_id=%s "
                    "conversation_id=%s error_type=%s",
                    request_id,
                    conversation_id,
                    type(exc).__name__,
                )
            try:
                with session.begin_nested():
                    extract_and_consolidate_turn(
                        session,
                        conversation_id=conversation_id,
                        namespace=namespace,
                        source_turn_id=source_turn_id,
                        user_message=user_message,
                    )
            except Exception as exc:
                logger.warning(
                    "background_memory_extraction_failed request_id=%s "
                    "conversation_id=%s error_type=%s",
                    request_id,
                    conversation_id,
                    type(exc).__name__,
                )
            session.commit()
    except Exception as exc:
        error = exc
        session.rollback()
        logger.warning(
            "background_memory_processing_failed request_id=%s "
            "conversation_id=%s error_type=%s",
            request_id,
            conversation_id,
            type(exc).__name__,
        )
    finally:
        session.close()
        trace.finish()
        payload = trace.summary(
            event=(
                "agent_memory_post_processing_failed"
                if error is not None
                else "agent_memory_post_processing_completed"
            ),
            error=error,
        )
        logger.info(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
