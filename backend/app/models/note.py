import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Note(Base):
    """A database-backed LaTeX note managed inside the app."""

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_library_item_id", "library_item_id"),
        Index("ix_notes_status", "status"),
        Index("ix_notes_created_at", "created_at"),
        CheckConstraint("title <> ''", name="ck_notes_title_non_empty"),
        CheckConstraint(
            "content_latex IS NOT NULL", name="ck_notes_content_latex_required"
        ),
        CheckConstraint("status <> ''", name="ck_notes_status_non_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_latex: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    library_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_items.id"), nullable=True
    )
    source_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_tags: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default="active"
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
