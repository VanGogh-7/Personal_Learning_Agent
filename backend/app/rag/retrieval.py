import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.vector_search import search_similar_chunks, search_similar_chunks_for_documents
from app.db.vector_search import DEFAULT_EXCLUDED_SECTION_TYPES
from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from app.observability.latency import (
    current_latency_trace,
    get_request_query_embedding,
    measure_latency_sync,
)


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
    document_source_path: str | None = None
    library_item_id: uuid.UUID | None = None
    library_title: str | None = None
    library_author: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_type: str = "unknown"
    chapter_title: str | None = None
    section_title: str | None = None


@dataclass
class LibraryItemRagContext:
    item_id: uuid.UUID
    title: str
    author: str | None
    file_type: str | None
    status: str


class LibraryItemRagError(ValueError):
    """Raised when a library-scoped RAG query cannot be served."""


def resolve_library_item_rag_context(
    session: Session,
    library_item_id: uuid.UUID,
) -> LibraryItemRagContext:
    """Validate that one Library item is searchable for RAG."""
    item = session.get(LibraryItem, library_item_id)
    if item is None:
        raise LibraryItemRagError("Library item not found")

    with measure_latency_sync("document_chunk_load"):
        documents = session.execute(
            select(Document).where(Document.library_item_id == item.id)
        ).scalars().all()
    if not documents:
        raise LibraryItemRagError("Library item has not been indexed yet.")

    document_ids = [document.id for document in documents]
    document_ids_with_embeddings = set(
        session.execute(
            select(DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(document_ids))
            .where(DocumentChunk.embedding.is_not(None))
        )
        .scalars()
        .all()
    )
    if not document_ids_with_embeddings:
        raise LibraryItemRagError("Library item has no indexed chunks to search.")

    return LibraryItemRagContext(
        item_id=item.id,
        title=item.title,
        author=item.author,
        file_type=item.file_type,
        status=item.status,
    )


def resolve_library_items_rag_context(
    session: Session,
    library_item_ids: list[uuid.UUID],
) -> list[LibraryItemRagContext]:
    """Validate that selected Library items are searchable for RAG."""
    deduped_item_ids = list(dict.fromkeys(library_item_ids))
    if not deduped_item_ids:
        raise LibraryItemRagError("library_item_ids must not be empty")

    with measure_latency_sync("document_chunk_load"):
        items = session.execute(
            select(LibraryItem).where(LibraryItem.id.in_(deduped_item_ids))
        ).scalars().all()
    items_by_id = {item.id: item for item in items}

    for item_id in deduped_item_ids:
        if item_id not in items_by_id:
            raise LibraryItemRagError("Library item not found")

    with measure_latency_sync("document_chunk_load"):
        documents = session.execute(
            select(Document).where(Document.library_item_id.in_(deduped_item_ids))
        ).scalars().all()
    documents_by_item_id: dict[uuid.UUID, list[Document]] = {
        item_id: [] for item_id in deduped_item_ids
    }
    for document in documents:
        if document.library_item_id in documents_by_item_id:
            documents_by_item_id[document.library_item_id].append(document)

    for item_id in deduped_item_ids:
        if not documents_by_item_id[item_id]:
            item = items_by_id[item_id]
            raise LibraryItemRagError(
                f"Library item has not been indexed yet: {item.title}"
            )

    document_ids = [document.id for document in documents]
    document_ids_with_embeddings = set(
        session.execute(
            select(DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(document_ids))
            .where(DocumentChunk.embedding.is_not(None))
        )
        .scalars()
        .all()
    )

    for item_id in deduped_item_ids:
        if not any(
            document.id in document_ids_with_embeddings
            for document in documents_by_item_id[item_id]
        ):
            item = items_by_id[item_id]
            raise LibraryItemRagError(
                f"Library item has no indexed chunks to search: {item.title}"
            )

    return [
        LibraryItemRagContext(
            item_id=item.id,
            title=item.title,
            author=item.author,
            file_type=item.file_type,
            status=item.status,
        )
        for item in (items_by_id[item_id] for item_id in deduped_item_ids)
    ]


def retrieve_relevant_chunks(
    session: Session,
    question: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
    include_non_body: bool = False,
) -> list[RetrievedChunkResult]:
    """Embed the question and retrieve the most similar document chunks.

    Uses the configured embedding provider unless a provider is passed in
    explicitly. Tests force the mock provider through environment setup.
    """
    provider = embedding_provider or get_embedding_provider()
    query_embedding = get_request_query_embedding(provider, question)

    exclude_section_types = () if include_non_body else DEFAULT_EXCLUDED_SECTION_TYPES
    with measure_latency_sync("document_vector_search"):
        similar_chunks = search_similar_chunks(
            session,
            query_embedding,
            limit=top_k,
            exclude_section_types=exclude_section_types,
        )
    if not similar_chunks:
        return []

    with measure_latency_sync("document_chunk_load"):
        document_ids = {chunk.document_id for chunk in similar_chunks}
        documents = {
            document.id: document
            for document in session.execute(
                select(Document).where(Document.id.in_(document_ids))
            ).scalars()
        }

        library_item_ids = {
            document.library_item_id
            for document in documents.values()
            if document.library_item_id
        }
        library_items = (
            {
                item.id: item
                for item in session.execute(
                    select(LibraryItem).where(LibraryItem.id.in_(library_item_ids))
                ).scalars()
            }
            if library_item_ids
            else {}
        )

    results: list[RetrievedChunkResult] = []
    for chunk in similar_chunks:
        document = documents.get(chunk.document_id)
        library_item = (
            library_items.get(document.library_item_id)
            if document is not None and document.library_item_id
            else None
        )
        results.append(
            RetrievedChunkResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=document.title if document else None,
                document_source_path=document.file_path if document else None,
                library_item_id=document.library_item_id if document else None,
                library_title=library_item.title if library_item else None,
                library_author=library_item.author if library_item else None,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                score=chunk.distance,
            )
        )

    return results


def retrieve_relevant_chunks_for_library_item(
    session: Session,
    library_item_id: uuid.UUID,
    question: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
    include_non_body: bool = False,
) -> tuple[LibraryItemRagContext, list[RetrievedChunkResult]]:
    """Retrieve chunks only from documents associated with one Library item."""
    item = session.get(LibraryItem, library_item_id)
    if item is None:
        raise LibraryItemRagError("Library item not found")

    with measure_latency_sync("document_chunk_load"):
        documents = session.execute(
            select(Document).where(Document.library_item_id == item.id)
        ).scalars().all()
    if not documents:
        raise LibraryItemRagError("Library item has not been indexed yet.")

    provider = embedding_provider or get_embedding_provider()
    query_embedding = get_request_query_embedding(provider, question)
    document_ids = [document.id for document in documents]
    exclude_section_types = () if include_non_body else DEFAULT_EXCLUDED_SECTION_TYPES
    with measure_latency_sync("document_vector_search"):
        similar_chunks = search_similar_chunks_for_documents(
            session,
            query_embedding,
            document_ids=document_ids,
            limit=top_k,
            exclude_section_types=exclude_section_types,
        )
    if not similar_chunks:
        raise LibraryItemRagError("Library item has no indexed chunks to search.")

    documents_by_id = {document.id: document for document in documents}
    context = LibraryItemRagContext(
        item_id=item.id,
        title=item.title,
        author=item.author,
        file_type=item.file_type,
        status=item.status,
    )

    results: list[RetrievedChunkResult] = []
    for chunk in similar_chunks:
        document = documents_by_id.get(chunk.document_id)
        results.append(
            RetrievedChunkResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=document.title if document else None,
                document_source_path=document.file_path if document else None,
                library_item_id=item.id,
                library_title=item.title,
                library_author=item.author,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                score=chunk.distance,
            )
        )

    return context, results


def retrieve_relevant_chunks_for_library_items(
    session: Session,
    library_item_ids: list[uuid.UUID],
    question: str,
    top_k: int = 5,
    embedding_provider: EmbeddingProvider | None = None,
    include_non_body: bool = False,
) -> tuple[list[LibraryItemRagContext], list[RetrievedChunkResult]]:
    """Retrieve chunks only from documents associated with selected Library items."""
    deduped_item_ids = list(dict.fromkeys(library_item_ids))
    if not deduped_item_ids:
        raise LibraryItemRagError("library_item_ids must not be empty")

    with measure_latency_sync("document_chunk_load"):
        items = session.execute(
            select(LibraryItem).where(LibraryItem.id.in_(deduped_item_ids))
        ).scalars().all()
    items_by_id = {item.id: item for item in items}

    for item_id in deduped_item_ids:
        if item_id not in items_by_id:
            raise LibraryItemRagError("Library item not found")

    with measure_latency_sync("document_chunk_load"):
        documents = session.execute(
            select(Document).where(Document.library_item_id.in_(deduped_item_ids))
        ).scalars().all()
    documents_by_item_id: dict[uuid.UUID, list[Document]] = {
        item_id: [] for item_id in deduped_item_ids
    }
    for document in documents:
        if document.library_item_id in documents_by_item_id:
            documents_by_item_id[document.library_item_id].append(document)

    for item_id in deduped_item_ids:
        if not documents_by_item_id[item_id]:
            item = items_by_id[item_id]
            raise LibraryItemRagError(
                f"Library item has not been indexed yet: {item.title}"
            )

    document_ids = [document.id for document in documents]
    document_ids_with_embeddings = set(
        session.execute(
            select(DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(document_ids))
            .where(DocumentChunk.embedding.is_not(None))
        )
        .scalars()
        .all()
    )

    for item_id in deduped_item_ids:
        if not any(
            document.id in document_ids_with_embeddings
            for document in documents_by_item_id[item_id]
        ):
            item = items_by_id[item_id]
            raise LibraryItemRagError(
                f"Library item has no indexed chunks to search: {item.title}"
            )

    provider = embedding_provider or get_embedding_provider()
    query_embedding = get_request_query_embedding(provider, question)
    exclude_section_types = () if include_non_body else DEFAULT_EXCLUDED_SECTION_TYPES
    with measure_latency_sync("document_vector_search"):
        similar_chunks = search_similar_chunks_for_documents(
            session,
            query_embedding,
            document_ids=document_ids,
            limit=top_k,
            exclude_section_types=exclude_section_types,
        )
    if not similar_chunks:
        raise LibraryItemRagError("Selected library items have no indexed chunks to search.")

    documents_by_id = {document.id: document for document in documents}
    contexts = [
        LibraryItemRagContext(
            item_id=item.id,
            title=item.title,
            author=item.author,
            file_type=item.file_type,
            status=item.status,
        )
        for item in (items_by_id[item_id] for item_id in deduped_item_ids)
    ]

    results: list[RetrievedChunkResult] = []
    for chunk in similar_chunks:
        document = documents_by_id.get(chunk.document_id)
        item = (
            items_by_id.get(document.library_item_id)
            if document is not None and document.library_item_id is not None
            else None
        )
        results.append(
            RetrievedChunkResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=document.title if document else None,
                document_source_path=document.file_path if document else None,
                library_item_id=item.id if item else None,
                library_title=item.title if item else None,
                library_author=item.author if item else None,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                score=chunk.distance,
            )
        )

    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter("retrieved_chunk_count", len(results))
    return contexts, results
