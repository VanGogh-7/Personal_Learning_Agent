import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LibraryItem(Base):
    """A manually registered book or learning material metadata record.

    Stage 10 stores metadata only. It does not open files, parse
    documents, create embeddings, or index contents.
    """

    __tablename__ = "library_items"
    __table_args__ = (
        Index("ix_library_items_title", "title"),
        Index("ix_library_items_status", "status"),
        Index("ix_library_items_created_at", "created_at"),
        CheckConstraint("title <> ''", name="ck_library_items_title_non_empty"),
        CheckConstraint("status <> ''", name="ck_library_items_status_non_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_tags: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="registered", server_default="registered"
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
