"""add learning events table

Revision ID: 6a8c3d4e5f01
Revises: b4a2f1c8d9e0
Create Date: 2026-07-06 18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a8c3d4e5f01"
down_revision: Union[str, None] = "b4a2f1c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "learning_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("library_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_item_id"],
            ["library_items.id"],
            name="fk_learning_events_library_item_id_library_items",
        ),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name="fk_learning_events_note_id_notes",
        ),
        sa.CheckConstraint(
            "event_type <> ''", name="ck_learning_events_event_type_non_empty"
        ),
        sa.CheckConstraint("title <> ''", name="ck_learning_events_title_non_empty"),
    )
    op.create_index(
        "ix_learning_events_event_type", "learning_events", ["event_type"]
    )
    op.create_index(
        "ix_learning_events_source_type", "learning_events", ["source_type"]
    )
    op.create_index("ix_learning_events_source_id", "learning_events", ["source_id"])
    op.create_index(
        "ix_learning_events_library_item_id", "learning_events", ["library_item_id"]
    )
    op.create_index("ix_learning_events_note_id", "learning_events", ["note_id"])
    op.create_index("ix_learning_events_session_id", "learning_events", ["session_id"])
    op.create_index("ix_learning_events_created_at", "learning_events", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_learning_events_created_at", table_name="learning_events")
    op.drop_index("ix_learning_events_session_id", table_name="learning_events")
    op.drop_index("ix_learning_events_note_id", table_name="learning_events")
    op.drop_index("ix_learning_events_library_item_id", table_name="learning_events")
    op.drop_index("ix_learning_events_source_id", table_name="learning_events")
    op.drop_index("ix_learning_events_source_type", table_name="learning_events")
    op.drop_index("ix_learning_events_event_type", table_name="learning_events")
    op.drop_table("learning_events")
