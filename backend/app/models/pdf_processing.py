import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PdfProcessingVersion(Base):
    """Immutable PDF extraction/OCR/layout processing attempt."""

    __tablename__ = "pdf_processing_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    pdf_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="extraction_failed"
    )
    detection_evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parser_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    ocr_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    text_index_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embedding_index_versions.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DocumentPage(Base):
    """Page-aware extracted text and bounded layout/OCR metadata."""

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "processing_version_id",
            "page_number",
            name="uq_document_pages_version_page",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    processing_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pdf_processing_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bounding_boxes: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list
    )
    text_character_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    image_coverage_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, default=0
    )
    width_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class VisualIndexVersion(Base):
    """Experimental visual page vector space, isolated from text embeddings."""

    __tablename__ = "visual_index_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processing_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pdf_processing_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    index_format: Mapped[str] = mapped_column(
        String(40), nullable=False, default="late_interaction"
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VisualPageEmbedding(Base):
    """Bounded experimental page vectors; JSON supports mock multi-vectors."""

    __tablename__ = "visual_page_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "visual_index_version_id",
            "document_page_id",
            name="uq_visual_page_embeddings_version_page",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visual_index_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visual_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
