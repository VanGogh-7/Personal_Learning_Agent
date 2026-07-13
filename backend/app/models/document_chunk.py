import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Float,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.embeddings.base import EMBEDDING_DIMENSION


class DocumentChunk(Base):
    """A chunk generated from a document, with an optional embedding
    vector for pgvector similarity search (Stage 4)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "processing_version_id",
            "chunk_index",
            name="uq_document_chunks_document_version_chunk_index",
        ),
        Index(
            "uq_document_chunks_legacy_document_chunk_index",
            "document_id",
            "chunk_index",
            unique=True,
            postgresql_where=text("processing_version_id IS NULL"),
            sqlite_where=text("processing_version_id IS NULL"),
        ),
        Index("ix_document_chunks_document_id", "document_id"),
        Index(
            "ix_document_chunks_embedding_1024_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_l2_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
        CheckConstraint(
            "char_start >= 0", name="ck_document_chunks_char_start_non_negative"
        ),
        CheckConstraint(
            "char_end >= 0", name="ck_document_chunks_char_end_non_negative"
        ),
        CheckConstraint(
            "char_end >= char_start", name="ck_document_chunks_char_end_gte_char_start"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_type: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    chapter_title: Mapped[str | None] = mapped_column(String, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String, nullable=True)
    processing_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pdf_processing_versions.id"),
        nullable=True,
        index=True,
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    element_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="paragraph"
    )
    section_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    bounding_boxes: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list
    )
    extraction_method: Mapped[str] = mapped_column(
        String(40), nullable=False, default="text"
    )
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Nullable: existing chunks may not have an embedding yet.
    embedding_2048: Mapped[list[float] | None] = mapped_column(
        Vector(2048), nullable=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
