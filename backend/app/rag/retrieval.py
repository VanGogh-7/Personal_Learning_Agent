import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.vector_search import search_similar_chunks, search_similar_chunks_for_documents
from app.embeddings.base import EmbeddingProvider
from app.embeddings.mock import MockEmbeddingProvider
from app.models.document import Document
from app.models.library_item import LibraryItem


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


@dataclass
class LibraryItemRagContext:
    item_id: uuid.UUID
    title: str
    author: str | None
    file_type: str | None
    status: str


class LibraryItemRagError(ValueError):
    """Raised when a library-scoped RAG query cannot be served."""


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


def retrieve_relevant_chunks_for_library_item(
    session: Session,
    library_item_id: uuid.UUID,
    question: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
) -> tuple[LibraryItemRagContext, list[RetrievedChunkResult]]:
    """Retrieve chunks only from documents associated with one Library item."""
    item = session.get(LibraryItem, library_item_id)
    if item is None:
        raise LibraryItemRagError("Library item not found")

    documents = session.execute(
        select(Document).where(Document.library_item_id == item.id)
    ).scalars().all()
    if not documents:
        raise LibraryItemRagError("Library item has not been indexed yet.")

    provider = embedding_provider or MockEmbeddingProvider()
    query_embedding = provider.embed_text(question)
    document_ids = [document.id for document in documents]
    similar_chunks = search_similar_chunks_for_documents(
        session, query_embedding, document_ids=document_ids, limit=top_k
    )
    if not similar_chunks:
        raise LibraryItemRagError("Library item has no indexed chunks to search.")

    document_titles = {document.id: document.title for document in documents}
    context = LibraryItemRagContext(
        item_id=item.id,
        title=item.title,
        author=item.author,
        file_type=item.file_type,
        status=item.status,
    )

    return context, [
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
