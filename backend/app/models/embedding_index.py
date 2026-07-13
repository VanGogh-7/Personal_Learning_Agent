import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.db.base import Base


class EmbeddingIndexVersion(Base):
    """A model-specific vector space that is activated only after re-indexing."""

    __tablename__ = "embedding_index_versions"
    __table_args__ = (
        Index(
            "ix_embedding_index_versions_profile_status",
            "embedding_profile_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    embedding_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_profiles.id"),
        nullable=False,
        index=True,
    )
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedded_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ChunkEmbedding(Base):
    """Versioned chunk vector; rows from different vector spaces never mix."""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id", "index_version_id", name="uq_chunk_embeddings_chunk_version"
        ),
        Index(
            "ix_chunk_embeddings_embedding_1024_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_l2_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_index_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_legacy: Mapped[list[float] | None] = mapped_column(
        Vector(), nullable=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
