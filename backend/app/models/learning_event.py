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


class LearningEvent(Base):
    """Append-only learning event used for the progress timeline."""

    __tablename__ = "learning_events"
    __table_args__ = (
        Index("ix_learning_events_event_type", "event_type"),
        Index("ix_learning_events_source_type", "source_type"),
        Index("ix_learning_events_source_id", "source_id"),
        Index("ix_learning_events_library_item_id", "library_item_id"),
        Index("ix_learning_events_note_id", "note_id"),
        Index("ix_learning_events_session_id", "session_id"),
        Index("ix_learning_events_created_at", "created_at"),
        CheckConstraint(
            "event_type <> ''", name="ck_learning_events_event_type_non_empty"
        ),
        CheckConstraint("title <> ''", name="ck_learning_events_title_non_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    library_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("library_items.id"), nullable=True
    )
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
