import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.vector_search import search_similar_chunks
from app.embeddings.base import EmbeddingProvider
from app.embeddings.mock import MockEmbeddingProvider
from app.models.document import Document


@dataclass
class RetrievedChunkResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str | None
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: float


def retrieve_relevant_chunks(
    session: Session,
    question: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunkResult]:
    """Embed the question and retrieve the most similar document chunks.

    Uses the deterministic mock embedding provider (unless a different
    provider is passed in) and the existing Stage 4 pgvector similarity
    search. Does not call external APIs.
    """
    provider = embedding_provider or MockEmbeddingProvider()
    query_embedding = provider.embed_text(question)

    similar_chunks = search_similar_chunks(session, query_embedding, limit=top_k)
    if not similar_chunks:
        return []

    document_titles: dict[uuid.UUID, str | None] = {}
    for chunk in similar_chunks:
        if chunk.document_id not in document_titles:
            document = session.get(Document, chunk.document_id)
            document_titles[chunk.document_id] = document.title if document else None

    return [
        RetrievedChunkResult(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_title=document_titles.get(chunk.document_id),
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            score=chunk.distance,
        )
        for chunk in similar_chunks
    ]
