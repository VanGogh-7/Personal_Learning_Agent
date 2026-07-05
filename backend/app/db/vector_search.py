import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document_chunk import DocumentChunk

MAX_SEARCH_LIMIT = 100


@dataclass
class SimilarChunkResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    distance: float


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


def build_similarity_query(query_embedding: Sequence[float], limit: int = 5) -> Select:
    """Build (without executing) a query for the nearest chunks by L2 distance.

    Only chunks with a stored embedding are considered.
    """
    _validate_embedding_dimension(query_embedding)
    _validate_limit(limit)

    distance = DocumentChunk.embedding.l2_distance(list(query_embedding))

    return (
        select(DocumentChunk, distance.label("distance"))
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )


def search_similar_chunks(
    session: Session, query_embedding: Sequence[float], limit: int = 5
) -> list[SimilarChunkResult]:
    """Return the chunks with embeddings closest to query_embedding (L2 distance)."""
    stmt = build_similarity_query(query_embedding, limit)
    rows = session.execute(stmt).all()

    return [
        SimilarChunkResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            distance=float(distance),
        )
        for chunk, distance in rows
    ]
