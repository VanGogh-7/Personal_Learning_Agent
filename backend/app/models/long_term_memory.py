import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.embeddings.base import EMBEDDING_DIMENSION


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
        Index("ix_long_term_memories_namespace_status", "namespace", "status"),
        Index("ix_long_term_memories_type_subtype", "memory_type", "memory_subtype"),
        CheckConstraint(
            "memory_type <> ''", name="ck_long_term_memories_memory_type_non_empty"
        ),
        CheckConstraint(
            "content <> ''", name="ck_long_term_memories_content_non_empty"
        ),
        CheckConstraint(
            "importance >= 1 AND importance <= 5",
            name="ck_long_term_memories_importance_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    memory_type: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(
        String, nullable=False, default="default_user", server_default="default_user"
    )
    subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    memory_subtype: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSONB on PostgreSQL; falls back to generic JSON for SQLite (used only
    # by unit tests, never in production).
    tags: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    structured_data: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    embedding_2048: Mapped[list[float] | None] = mapped_column(
        Vector(2048).with_variant(JSON(), "sqlite"), nullable=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0"
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default="active"
    )
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_turns.id"), nullable=True
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_events.id"), nullable=True
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("long_term_memories.id"), nullable=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
