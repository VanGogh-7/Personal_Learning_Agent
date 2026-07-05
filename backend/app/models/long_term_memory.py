import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LongTermMemory(Base):
    """A manually created long-term memory item.

    Stage 7: manual creation only. No automatic extraction, no
    promotion from short-term memory, no embeddings/vector search.
    """

    __tablename__ = "long_term_memories"
    __table_args__ = (
        Index("ix_long_term_memories_memory_type", "memory_type"),
        Index("ix_long_term_memories_importance", "importance"),
        Index("ix_long_term_memories_created_at", "created_at"),
        CheckConstraint("memory_type <> ''", name="ck_long_term_memories_memory_type_non_empty"),
        CheckConstraint("content <> ''", name="ck_long_term_memories_content_non_empty"),
        CheckConstraint(
            "importance >= 1 AND importance <= 5", name="ck_long_term_memories_importance_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    memory_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSONB on PostgreSQL; falls back to generic JSON for SQLite (used only
    # by unit tests, never in production).
    tags: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
