import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationTurn(Base):
    """A single short-term conversation turn (question + answer) for a
    session. Stage 6: short-term memory only, bounded by recency."""

    __tablename__ = "conversation_turns"
    __table_args__ = (
        Index("ix_conversation_turns_session_id", "session_id"),
        CheckConstraint("session_id <> ''", name="ck_conversation_turns_session_id_non_empty"),
        CheckConstraint("question <> ''", name="ck_conversation_turns_question_non_empty"),
        CheckConstraint("answer <> ''", name="ck_conversation_turns_answer_non_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # Stable ordering within a session, independent of timestamp resolution.
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSONB on PostgreSQL; falls back to generic JSON for SQLite (used only
    # by unit tests, never in production).
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
