import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Select, and_, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.models.embedding_index import ChunkEmbedding, EmbeddingIndexVersion
from app.models.provider_profile import ProviderProfile

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
    parent_chunk_id: uuid.UUID | None = None
    element_type: str = "paragraph"
    extraction_method: str = "text"
    ocr_confidence: float | None = None
    section_path: tuple[str, ...] = ()
    bounding_boxes: tuple[dict, ...] = ()


def _validate_embedding_dimension(embedding: Sequence[float]) -> None:
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding must have {EMBEDDING_DIMENSION} dimensions, got {len(embedding)}"
        )


def _validate_limit(limit: int, max_limit: int = MAX_SEARCH_LIMIT) -> None:
    if not (1 <= limit <= max_limit):
        raise ValueError(f"limit must be between 1 and {max_limit}, got {limit}")


def set_chunk_embedding(
    session: Session, chunk_id: uuid.UUID, embedding: Sequence[float]
) -> None:
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
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.embedding.is_not(None))
        .where(active_processing_filter())
        .order_by(distance)
        .limit(limit)
    )
    if exclude_section_types:
        stmt = stmt.where(
            DocumentChunk.section_type.not_in(list(exclude_section_types))
        )
    return stmt


def search_similar_chunks(
    session: Session,
    query_embedding: Sequence[float],
    limit: int = 5,
    exclude_section_types: Sequence[str] = DEFAULT_EXCLUDED_SECTION_TYPES,
) -> list[SimilarChunkResult]:
    """Return the chunks with embeddings closest to query_embedding (L2 distance)."""
    version_id = resolve_active_embedding_index_version_id(session)
    if version_id is not None:
        document_ids = (
            session.execute(select(DocumentChunk.document_id).distinct())
            .scalars()
            .all()
        )
        return _search_versioned_chunks_for_documents(
            session,
            query_embedding,
            document_ids,
            uuid.UUID(version_id),
            limit,
            exclude_section_types,
            force_ann=True,
        )
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
            parent_chunk_id=chunk.parent_chunk_id,
            element_type=chunk.element_type,
            extraction_method=chunk.extraction_method,
            ocr_confidence=chunk.ocr_confidence,
            section_path=tuple(chunk.section_path or ()),
            bounding_boxes=tuple(chunk.bounding_boxes or ()),
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
    force_ann: bool | None = None,
) -> list[SimilarChunkResult]:
    """Return nearest embedded chunks restricted to a set of documents.

    The global search path uses pgvector ordering directly. For the
    Stage 15 scoped path, this helper first filters to a small explicit
    document set and then applies the same L2 distance deterministically
    in Python. This keeps tests portable across SQLite and PostgreSQL
    while still using the embeddings persisted on document chunks.
    """
    version_id = resolve_active_embedding_index_version_id(session)
    if version_id is None:
        _validate_embedding_dimension(query_embedding)
    elif not query_embedding:
        raise ValueError("Embedding must not be empty")
    _validate_limit(limit)
    if not document_ids:
        return []

    if version_id is not None:
        use_ann = (
            len(document_ids) > get_settings().local_exact_search_max_documents
            if force_ann is None
            else force_ann
        )
        return _search_versioned_chunks_for_documents(
            session,
            query_embedding,
            document_ids,
            uuid.UUID(version_id),
            limit,
            exclude_section_types,
            force_ann=use_ann,
        )

    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(list(document_ids)))
        .where(DocumentChunk.embedding.is_not(None))
        .where(active_processing_filter())
    )
    if exclude_section_types:
        stmt = stmt.where(
            DocumentChunk.section_type.not_in(list(exclude_section_types))
        )

    if (
        session.bind is not None
        and session.bind.dialect.name == "postgresql"
        and (
            len(document_ids) > get_settings().local_exact_search_max_documents
            if force_ann is None
            else force_ann
        )
    ):
        distance = DocumentChunk.embedding.l2_distance(list(query_embedding))
        vector_stmt = (
            select(DocumentChunk, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(list(document_ids)))
            .where(DocumentChunk.embedding.is_not(None))
            .where(active_processing_filter())
            .order_by(distance)
            .limit(limit)
        )
        if exclude_section_types:
            vector_stmt = vector_stmt.where(
                DocumentChunk.section_type.not_in(list(exclude_section_types))
            )
        vector_rows = session.execute(vector_stmt).all()
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
                parent_chunk_id=chunk.parent_chunk_id,
                element_type=chunk.element_type,
                extraction_method=chunk.extraction_method,
                ocr_confidence=chunk.ocr_confidence,
                section_path=tuple(chunk.section_path or ()),
                bounding_boxes=tuple(chunk.bounding_boxes or ()),
                distance=float(distance_value),
            )
            for chunk, distance_value in vector_rows
        ]

    rows = session.execute(stmt).scalars().all()

    scored = [
        (
            chunk,
            _l2_distance(
                query_embedding, chunk.embedding if chunk.embedding is not None else []
            ),
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
            parent_chunk_id=chunk.parent_chunk_id,
            element_type=chunk.element_type,
            extraction_method=chunk.extraction_method,
            ocr_confidence=chunk.ocr_confidence,
            section_path=tuple(chunk.section_path or ()),
            bounding_boxes=tuple(chunk.bounding_boxes or ()),
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


def document_ids_with_embeddings(
    session: Session, document_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Return searchable documents in only the active vector space."""
    version_id = resolve_active_embedding_index_version_id(session)
    if version_id is None:
        stmt = (
            select(DocumentChunk.document_id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(list(document_ids)))
            .where(DocumentChunk.embedding.is_not(None))
            .where(active_processing_filter())
        )
    else:
        embedding_column, _ = _version_embedding_column(session, uuid.UUID(version_id))
        stmt = (
            select(DocumentChunk.document_id)
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(list(document_ids)))
            .where(ChunkEmbedding.index_version_id == uuid.UUID(version_id))
            .where(embedding_column.is_not(None))
            .where(active_processing_filter())
        )
    return set(session.execute(stmt).scalars().all())


def _search_versioned_chunks_for_documents(
    session: Session,
    query_embedding: Sequence[float],
    document_ids: Sequence[uuid.UUID],
    version_id: uuid.UUID,
    limit: int,
    exclude_section_types: Sequence[str],
    *,
    force_ann: bool = False,
) -> list[SimilarChunkResult]:
    embedding_column, dimension = _version_embedding_column(session, version_id)
    if len(query_embedding) != dimension:
        raise ValueError(
            f"Embedding dimensions do not match: query {len(query_embedding)}, "
            f"index {dimension}"
        )
    if (
        session.bind is not None
        and session.bind.dialect.name == "postgresql"
        and force_ann
    ):
        if dimension == 1024:
            session.execute(
                text(f"SET LOCAL hnsw.ef_search = {get_settings().hnsw_ef_search}")
            )
        distance = embedding_column.l2_distance(list(query_embedding))
        stmt = (
            select(DocumentChunk, distance.label("distance"))
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(list(document_ids)))
            .where(ChunkEmbedding.index_version_id == version_id)
            .where(embedding_column.is_not(None))
            .where(active_processing_filter())
            .order_by(distance)
            .limit(limit)
        )
        if exclude_section_types:
            stmt = stmt.where(
                DocumentChunk.section_type.not_in(list(exclude_section_types))
            )
        return [
            _similar_result(chunk, float(distance_value))
            for chunk, distance_value in session.execute(stmt).all()
        ]
    stmt = (
        select(DocumentChunk, embedding_column)
        .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(list(document_ids)))
        .where(ChunkEmbedding.index_version_id == version_id)
        .where(embedding_column.is_not(None))
        .where(active_processing_filter())
    )
    if exclude_section_types:
        stmt = stmt.where(
            DocumentChunk.section_type.not_in(list(exclude_section_types))
        )
    scored = [
        (chunk, _dynamic_l2(query_embedding, vector))
        for chunk, vector in session.execute(stmt).all()
    ]
    scored.sort(key=lambda item: item[1])
    return [_similar_result(chunk, distance) for chunk, distance in scored[:limit]]


def _similar_result(chunk: DocumentChunk, distance: float) -> SimilarChunkResult:
    return SimilarChunkResult(
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
        parent_chunk_id=chunk.parent_chunk_id,
        element_type=chunk.element_type,
        extraction_method=chunk.extraction_method,
        ocr_confidence=chunk.ocr_confidence,
        section_path=tuple(chunk.section_path or ()),
        bounding_boxes=tuple(chunk.bounding_boxes or ()),
        distance=float(distance),
    )


def _active_embedding_index_version_id() -> str | None:
    from app.settings.runtime import current_embedding_index_version_id

    return current_embedding_index_version_id()


def resolve_active_embedding_index_version_id(session: Session) -> str | None:
    """Resolve the runtime vector space or the exact matching `.env` fallback.

    Runtime clients carry their version explicitly. After a process restart,
    Stronghold-backed clients are intentionally locked, so the Backend may use
    only a persisted active index whose provider, model, and dimension exactly
    match the non-secret `.env` fallback configuration.
    """
    runtime_version = _active_embedding_index_version_id()
    if runtime_version is not None:
        return runtime_version
    settings = get_settings()
    provider = settings.embedding_provider.strip().lower()
    if provider != "zhipu":
        return None
    version_id = session.scalar(
        select(EmbeddingIndexVersion.id)
        .join(
            ProviderProfile,
            ProviderProfile.id == EmbeddingIndexVersion.embedding_profile_id,
        )
        .where(ProviderProfile.kind == "embedding")
        .where(ProviderProfile.is_active.is_(True))
        .where(ProviderProfile.provider == provider)
        .where(ProviderProfile.model == settings.zhipu_embedding_model)
        .where(
            ProviderProfile.embedding_dimension == settings.zhipu_embedding_dimension
        )
        .where(EmbeddingIndexVersion.dimension == settings.zhipu_embedding_dimension)
        .where(EmbeddingIndexVersion.status == "active")
        .order_by(EmbeddingIndexVersion.completed_at.desc())
        .limit(1)
    )
    return str(version_id) if version_id is not None else None


def _version_embedding_column(session: Session, version_id: uuid.UUID):
    dimension = session.scalar(
        select(EmbeddingIndexVersion.dimension).where(
            EmbeddingIndexVersion.id == version_id
        )
    )
    if dimension is None:
        raise ValueError("Embedding index version was not found")
    return (
        ChunkEmbedding.embedding
        if dimension == 1024
        else ChunkEmbedding.embedding_legacy,
        int(dimension),
    )


def _dynamic_l2(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError(
            f"Embedding dimensions do not match: query {len(left)}, stored {len(right)}"
        )
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def active_processing_filter():
    """Select one successful PDF processing version or the legacy null space."""
    return or_(
        and_(
            Document.active_processing_version_id.is_(None),
            DocumentChunk.processing_version_id.is_(None),
        ),
        DocumentChunk.processing_version_id == Document.active_processing_version_id,
    )
