import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    """Product conversation mapped to an internal LangGraph thread."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_namespace_subject", "namespace", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    namespace: Mapped[str] = mapped_column(
        String, nullable=False, default="default_user", server_default="default_user"
    )
    subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    legacy_session_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True
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
