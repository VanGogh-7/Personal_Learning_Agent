import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.memory.extraction import MemoryCandidate
from app.memory.models import MemoryAction, MemoryStatus
from app.memory.repository import find_active_related_records
from app.models.long_term_memory import LongTermMemory


@dataclass(frozen=True)
class ConsolidationResult:
    action: MemoryAction
    memory_id: uuid.UUID | None = None
    superseded_id: uuid.UUID | None = None


def consolidate_candidate(
    session: Session,
    *,
    namespace: str,
    candidate: MemoryCandidate,
    source_turn_id: uuid.UUID | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    settings: Settings | None = None,
) -> ConsolidationResult:
    """Create, update, supersede, or ignore one validated candidate."""
    resolved = settings or get_settings()
    if not _passes_write_policy(candidate, resolved):
        return ConsolidationResult(MemoryAction.IGNORE)

    provider = embedding_provider or get_embedding_provider(resolved)
    embedding = provider.embed_text(candidate.content)
    related = find_active_related_records(
        session,
        namespace=namespace,
        memory_type=candidate.memory_type.value,
        memory_subtype=candidate.memory_subtype.value,
    )
    predicate = candidate.structured_data.get("predicate")
    scope = candidate.structured_data.get("scope") or candidate.scope
    object_value = candidate.structured_data.get("object")

    for existing in related:
        data = existing.structured_data or {}
        same_predicate = predicate and data.get("predicate") == predicate
        same_scope = (data.get("scope") or None) == (scope or None)
        same_object = _normalize(data.get("object")) == _normalize(object_value)
        stored_embedding = (
            list(existing.embedding) if existing.embedding is not None else []
        )
        similarity = _cosine_similarity(embedding, stored_embedding)

        if same_predicate and same_scope and same_object:
            existing.confidence = max(existing.confidence, candidate.confidence)
            existing.importance = max(
                existing.importance, _stored_importance(candidate.importance)
            )
            existing.structured_data = {**data, **candidate.structured_data}
            existing.embedding = embedding
            existing.updated_at = datetime.now(timezone.utc)
            session.flush()
            return ConsolidationResult(MemoryAction.UPDATE, existing.id)

        if same_predicate and same_scope and candidate.explicit:
            new_memory = _new_memory(
                namespace=namespace,
                candidate=candidate,
                embedding=embedding,
                source_turn_id=source_turn_id,
                supersedes_id=existing.id,
            )
            existing.status = MemoryStatus.SUPERSEDED
            existing.updated_at = datetime.now(timezone.utc)
            session.add(new_memory)
            session.flush()
            return ConsolidationResult(
                MemoryAction.SUPERSEDE, new_memory.id, existing.id
            )

        if similarity >= 0.96:
            existing.confidence = max(existing.confidence, candidate.confidence)
            existing.importance = max(
                existing.importance, _stored_importance(candidate.importance)
            )
            existing.updated_at = datetime.now(timezone.utc)
            session.flush()
            return ConsolidationResult(MemoryAction.UPDATE, existing.id)

    memory = _new_memory(
        namespace=namespace,
        candidate=candidate,
        embedding=embedding,
        source_turn_id=source_turn_id,
    )
    session.add(memory)
    session.flush()
    return ConsolidationResult(MemoryAction.CREATE, memory.id)


def _passes_write_policy(candidate: MemoryCandidate, settings: Settings) -> bool:
    if candidate.sensitive:
        return False
    if candidate.explicit:
        return True
    return (
        settings.memory_auto_write_enabled
        and candidate.importance >= settings.memory_auto_write_min_importance
        and candidate.confidence >= settings.memory_auto_write_min_confidence
        and candidate.durability >= settings.memory_auto_write_min_durability
    )


def _new_memory(
    *,
    namespace: str,
    candidate: MemoryCandidate,
    embedding: list[float],
    source_turn_id: uuid.UUID | None,
    supersedes_id: uuid.UUID | None = None,
) -> LongTermMemory:
    return LongTermMemory(
        namespace=namespace,
        memory_type=candidate.memory_type.value,
        memory_subtype=candidate.memory_subtype.value,
        content=candidate.content,
        structured_data=candidate.structured_data,
        embedding=embedding,
        importance=_stored_importance(candidate.importance),
        confidence=candidate.confidence,
        status=MemoryStatus.ACTIVE,
        source="explicit" if candidate.explicit else "automatic",
        source_type="conversation_turn",
        source_turn_id=source_turn_id,
        supersedes_id=supersedes_id,
        valid_from=datetime.now(timezone.utc),
    )


def _stored_importance(value: float) -> int:
    return max(1, min(5, round(value * 5)))


def _normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
