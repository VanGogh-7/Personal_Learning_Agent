import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.long_term_memory import LongTermMemory
from app.embeddings.providers import get_embedding_provider
from app.core.config import get_settings

MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 5
DEFAULT_IMPORTANCE = 3

DEFAULT_LIST_LIMIT = 20
MIN_LIST_LIMIT = 1
MAX_LIST_LIMIT = 50

# Bounded: only a small number of memories are ever used as context.
DEFAULT_CONTEXT_MEMORY_COUNT = 3


@dataclass
class LongTermMemoryResult:
    memory_id: uuid.UUID
    memory_type: str
    content: str
    importance: int
    source: str | None
    tags: list[str] | None
    created_at: datetime
    updated_at: datetime
    namespace: str = "default_user"
    subject_id: str | None = None
    memory_subtype: str | None = None
    structured_data: dict | None = None
    confidence: float = 1.0
    status: str = "active"
    source_type: str | None = None
    supersedes_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0


def _validate_memory_type(memory_type: str) -> None:
    if not memory_type or not memory_type.strip():
        raise ValueError("memory_type must not be empty")


def _validate_content(content: str) -> None:
    if not content or not content.strip():
        raise ValueError("content must not be empty")


def _validate_importance(importance: int) -> None:
    if not (MIN_IMPORTANCE <= importance <= MAX_IMPORTANCE):
        raise ValueError(
            f"importance must be between {MIN_IMPORTANCE} and {MAX_IMPORTANCE}"
        )


def _validate_limit(limit: int) -> None:
    if not (MIN_LIST_LIMIT <= limit <= MAX_LIST_LIMIT):
        raise ValueError(
            f"limit must be between {MIN_LIST_LIMIT} and {MAX_LIST_LIMIT}, got {limit}"
        )


def _to_result(memory: LongTermMemory) -> LongTermMemoryResult:
    return LongTermMemoryResult(
        memory_id=memory.id,
        memory_type=memory.memory_type,
        content=memory.content,
        importance=memory.importance,
        source=memory.source,
        tags=memory.tags,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        namespace=memory.namespace,
        subject_id=memory.subject_id,
        memory_subtype=memory.memory_subtype,
        structured_data=memory.structured_data,
        confidence=memory.confidence,
        status=memory.status,
        source_type=memory.source_type,
        supersedes_id=memory.supersedes_id,
        valid_from=memory.valid_from,
        valid_until=memory.valid_until,
        last_accessed_at=memory.last_accessed_at,
        access_count=memory.access_count,
    )


def create_memory(
    session: Session,
    memory_type: str,
    content: str,
    importance: int = DEFAULT_IMPORTANCE,
    source: str | None = "manual",
    tags: list[str] | None = None,
    namespace: str | None = None,
    subject_id: str | None = None,
    memory_subtype: str | None = None,
    structured_data: dict | None = None,
    confidence: float = 1.0,
    source_type: str | None = None,
) -> LongTermMemoryResult:
    """Create a long-term memory through the backward-compatible API helper.

    Does not commit; the caller controls the transaction boundary. Typed
    production writes normally flow through extraction and consolidation.
    """
    _validate_memory_type(memory_type)
    _validate_content(content)
    _validate_importance(importance)

    embedding = (
        get_embedding_provider().embed_text(content.strip()) if memory_subtype else None
    )
    memory = LongTermMemory(
        memory_type=memory_type.strip(),
        content=content.strip(),
        importance=importance,
        source=source,
        tags=list(tags) if tags is not None else None,
        namespace=namespace or get_settings().memory_default_namespace,
        subject_id=subject_id,
        memory_subtype=memory_subtype,
        structured_data=structured_data,
        embedding=embedding,
        confidence=confidence,
        status="active",
        source_type=source_type or source,
    )
    session.add(memory)
    session.flush()

    return _to_result(memory)


def get_memory(session: Session, memory_id: uuid.UUID) -> LongTermMemoryResult | None:
    """Return a single long-term memory by id, or None if not found."""
    memory = session.get(LongTermMemory, memory_id)
    return _to_result(memory) if memory is not None else None


def list_memories(
    session: Session,
    memory_type: str | None = None,
    min_importance: int | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    namespace: str | None = None,
    memory_subtype: str | None = None,
    status: str | None = None,
    offset: int = 0,
) -> list[LongTermMemoryResult]:
    """List memories, most recent first, optionally filtered by type/importance."""
    _validate_limit(limit)
    if min_importance is not None:
        _validate_importance(min_importance)

    stmt = select(LongTermMemory)
    if memory_type:
        stmt = stmt.where(LongTermMemory.memory_type == memory_type)
    if namespace:
        stmt = stmt.where(LongTermMemory.namespace == namespace)
    if memory_subtype:
        stmt = stmt.where(LongTermMemory.memory_subtype == memory_subtype)
    if status:
        stmt = stmt.where(LongTermMemory.status == status)
    if min_importance is not None:
        stmt = stmt.where(LongTermMemory.importance >= min_importance)
    stmt = stmt.order_by(LongTermMemory.created_at.desc()).offset(offset).limit(limit)

    rows = session.execute(stmt).scalars().all()
    return [_to_result(row) for row in rows]


def search_memories(
    session: Session,
    keyword: str,
    memory_type: str | None = None,
    min_importance: int | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
) -> list[LongTermMemoryResult]:
    """Simple case-insensitive keyword search over memory content.

    No embeddings or vector search: a plain SQL ILIKE match, bounded by
    `limit`, optionally filtered by memory_type/min_importance.
    """
    if not keyword or not keyword.strip():
        raise ValueError("keyword must not be empty")
    _validate_limit(limit)
    if min_importance is not None:
        _validate_importance(min_importance)

    pattern = f"%{keyword.strip()}%"
    stmt = select(LongTermMemory).where(LongTermMemory.content.ilike(pattern))
    if memory_type:
        stmt = stmt.where(LongTermMemory.memory_type == memory_type)
    if min_importance is not None:
        stmt = stmt.where(LongTermMemory.importance >= min_importance)
    stmt = stmt.order_by(LongTermMemory.created_at.desc()).limit(limit)

    rows = session.execute(stmt).scalars().all()
    return [_to_result(row) for row in rows]


def build_long_term_memory_context(memories: Sequence[LongTermMemoryResult]) -> str:
    """Build a simple, deterministic textual summary of long-term memories.

    Not an LLM summary: a small, bounded, human-readable listing. Does
    not call any external API.
    """
    if not memories:
        return ""

    bounded = list(memories)[:DEFAULT_CONTEXT_MEMORY_COUNT]
    lines = [f"[{memory.memory_type}] {memory.content.strip()}" for memory in bounded]
    return "\n".join(lines)
