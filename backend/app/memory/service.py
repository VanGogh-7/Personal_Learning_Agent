import logging
import time
import uuid

from sqlalchemy.orm import Session

from app.memory.consolidation import ConsolidationResult, consolidate_candidate
from app.memory.extraction import (
    ConservativeMemoryCandidateExtractor,
    MemoryCandidateExtractor,
)
from app.memory.summary import update_rolling_summary_if_needed

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
    candidates = resolved_extractor.extract(user_message)
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
