import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.memory.models import MemoryStatus, MemorySubtype, MemoryType
from app.models.long_term_memory import LongTermMemory
from app.observability.latency import get_request_query_embedding


@dataclass(frozen=True)
class RetrievedMemory:
    id: uuid.UUID
    memory_type: str
    memory_subtype: str | None
    content: str
    importance: float
    confidence: float
    score: float


def retrieve_memories(
    session: Session,
    *,
    namespace: str,
    query: str,
    memory_type: MemoryType | str | None = None,
    memory_subtype: MemorySubtype | str | None = None,
    predicate: str | None = None,
    scope: str | None = None,
    limit: int | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    semantic_search: bool = True,
    update_access: bool = True,
) -> list[RetrievedMemory]:
    """Retrieve a small namespace-isolated hybrid memory context."""
    settings = get_settings()
    bounded_limit = limit or settings.memory_retrieval_limit
    query_embedding: list[float] = []
    if semantic_search:
        provider = embedding_provider or get_embedding_provider(settings)
        query_embedding = get_request_query_embedding(provider, query)

    stmt = (
        select(LongTermMemory)
        .where(LongTermMemory.namespace == namespace)
        .where(LongTermMemory.status == MemoryStatus.ACTIVE)
        .where(
            or_(
                LongTermMemory.valid_until.is_(None),
                LongTermMemory.valid_until > datetime.now(timezone.utc),
            )
        )
    )
    if memory_type:
        stmt = stmt.where(LongTermMemory.memory_type == str(memory_type))
    if memory_subtype:
        stmt = stmt.where(LongTermMemory.memory_subtype == str(memory_subtype))
    candidates = list(
        session.execute(
            stmt.order_by(LongTermMemory.importance.desc()).limit(100)
        ).scalars()
    )
    candidate_by_id = {memory.id: memory for memory in candidates}
    if (
        query_embedding
        and session.bind is not None
        and session.bind.dialect.name == "postgresql"
    ):
        vector_stmt = (
            stmt.where(LongTermMemory.embedding.is_not(None))
            .order_by(LongTermMemory.embedding.cosine_distance(query_embedding))
            .limit(50)
        )
        for memory in session.execute(vector_stmt).scalars():
            candidate_by_id[memory.id] = memory
        keyword_terms = list(_tokens(query))[:8]
        if keyword_terms:
            keyword_stmt = stmt.where(
                or_(
                    *[
                        LongTermMemory.content.ilike(f"%{term}%")
                        for term in keyword_terms
                    ]
                )
            ).limit(50)
            for memory in session.execute(keyword_stmt).scalars():
                candidate_by_id[memory.id] = memory
    candidates = list(candidate_by_id.values())

    query_tokens = _tokens(query)
    scored: list[tuple[float, LongTermMemory]] = []
    now = datetime.now(timezone.utc)
    for memory in candidates:
        data = memory.structured_data or {}
        exact = 1.0 if predicate and data.get("predicate") == predicate else 0.0
        if exact and scope and data.get("scope") != scope:
            exact = 0.0
        stored_embedding = (
            list(memory.embedding) if memory.embedding is not None else []
        )
        semantic = max(0.0, _cosine_similarity(query_embedding, stored_embedding))
        keyword = _keyword_score(query_tokens, _tokens(memory.content))
        importance = memory.importance / 5.0
        created = memory.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - created).total_seconds() / 86400)
        recency = 1.0 / (1.0 + age_days / 180.0)
        score = (
            0.35 * semantic
            + 0.25 * keyword
            + 0.2 * importance
            + 0.1 * recency
            + 0.1 * exact
        )
        if exact == 0.0 and keyword == 0.0 and semantic < 0.2:
            continue
        scored.append((score, memory))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:bounded_limit]
    if update_access:
        for _, memory in selected:
            memory.last_accessed_at = now
            memory.access_count += 1
        session.flush()

    return [
        RetrievedMemory(
            id=memory.id,
            memory_type=memory.memory_type,
            memory_subtype=memory.memory_subtype,
            content=memory.content,
            importance=memory.importance / 5.0,
            confidence=memory.confidence,
            score=score,
        )
        for score, memory in selected
    ]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w+#]+", text) if len(token) > 1}


def _keyword_score(query: set[str], content: set[str]) -> float:
    return len(query & content) / len(query) if query else 0.0


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0
