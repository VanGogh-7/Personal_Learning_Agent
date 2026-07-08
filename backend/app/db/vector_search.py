import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document_chunk import DocumentChunk

MAX_SEARCH_LIMIT = 100
DEFAULT_EXCLUDED_SECTION_TYPES = ("contents", "index", "bibliography", "preface")


@dataclass
class SimilarChunkResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    distance: float
    page_start: int | None = None
    page_end: int | None = None
    section_type: str = "unknown"
    chapter_title: str | None = None
    section_title: str | None = None


def _validate_embedding_dimension(embedding: Sequence[float]) -> None:
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding must have {EMBEDDING_DIMENSION} dimensions, got {len(embedding)}"
        )


def _validate_limit(limit: int, max_limit: int = MAX_SEARCH_LIMIT) -> None:
    if not (1 <= limit <= max_limit):
        raise ValueError(f"limit must be between 1 and {max_limit}, got {limit}")


def set_chunk_embedding(session: Session, chunk_id: uuid.UUID, embedding: Sequence[float]) -> None:
    """Persist an embedding vector for a single document chunk.

    Does not commit; the caller controls the transaction boundary.
    """
    _validate_embedding_dimension(embedding)

    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None:
        raise ValueError(f"Document chunk '{chunk_id}' was not found")

    chunk.embedding = list(embedding)
    session.flush()


def build_similarity_query(
    query_embedding: Sequence[float],
    limit: int = 5,
    exclude_section_types: Sequence[str] = DEFAULT_EXCLUDED_SECTION_TYPES,
) -> Select:
    """Build (without executing) a query for the nearest chunks by L2 distance.

    Only chunks with a stored embedding are considered.
    """
    _validate_embedding_dimension(query_embedding)
    _validate_limit(limit)

    distance = DocumentChunk.embedding.l2_distance(list(query_embedding))

    stmt = (
        select(DocumentChunk, distance.label("distance"))
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    if exclude_section_types:
        stmt = stmt.where(DocumentChunk.section_type.not_in(list(exclude_section_types)))
    return stmt


def search_similar_chunks(
    session: Session,
    query_embedding: Sequence[float],
    limit: int = 5,
    exclude_section_types: Sequence[str] = DEFAULT_EXCLUDED_SECTION_TYPES,
) -> list[SimilarChunkResult]:
    """Return the chunks with embeddings closest to query_embedding (L2 distance)."""
    stmt = build_similarity_query(query_embedding, limit, exclude_section_types)
    rows = session.execute(stmt).all()

    return [
        SimilarChunkResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_type=chunk.section_type,
            chapter_title=chunk.chapter_title,
            section_title=chunk.section_title,
            distance=float(distance),
        )
        for chunk, distance in rows
    ]


def search_similar_chunks_for_documents(
    session: Session,
    query_embedding: Sequence[float],
    document_ids: Sequence[uuid.UUID],
    limit: int = 5,
    exclude_section_types: Sequence[str] = DEFAULT_EXCLUDED_SECTION_TYPES,
) -> list[SimilarChunkResult]:
    """Return nearest embedded chunks restricted to a set of documents.

    The global search path uses pgvector ordering directly. For the
    Stage 15 scoped path, this helper first filters to a small explicit
    document set and then applies the same L2 distance deterministically
    in Python. This keeps tests portable across SQLite and PostgreSQL
    while still using the embeddings persisted on document chunks.
    """
    _validate_embedding_dimension(query_embedding)
    _validate_limit(limit)
    if not document_ids:
        return []

    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id.in_(list(document_ids)))
        .where(DocumentChunk.embedding.is_not(None))
    )
    if exclude_section_types:
        stmt = stmt.where(DocumentChunk.section_type.not_in(list(exclude_section_types)))

    rows = (
        session.execute(stmt)
        .scalars()
        .all()
    )

    scored = [
        (
            chunk,
            _l2_distance(query_embedding, chunk.embedding if chunk.embedding is not None else []),
        )
        for chunk in rows
    ]
    scored.sort(key=lambda item: item[1])

    return [
        SimilarChunkResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_type=chunk.section_type,
            chapter_title=chunk.chapter_title,
            section_title=chunk.section_title,
            distance=float(distance),
        )
        for chunk, distance in scored[:limit]
    ]


def _l2_distance(left: Sequence[float], right: Sequence[float]) -> float:
    _validate_embedding_dimension(right)
    squared_distance = sum(
        (left_value - right_value) ** 2 for left_value, right_value in zip(left, right)
    )
    return squared_distance**0.5
