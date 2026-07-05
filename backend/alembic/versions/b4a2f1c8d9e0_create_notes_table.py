"""create notes table for Notes MVP

Revision ID: b4a2f1c8d9e0
Revises: 91b7d4e8c3a2
Create Date: 2026-07-06 16:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4a2f1c8d9e0"
down_revision: Union[str, None] = "91b7d4e8c3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content_latex", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("library_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_session_id", sa.String(), nullable=True),
        sa.Column("topic_tags", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_item_id"],
            ["library_items.id"],
            name="fk_notes_library_item_id_library_items",
        ),
        sa.CheckConstraint("title <> ''", name="ck_notes_title_non_empty"),
        sa.CheckConstraint(
            "content_latex IS NOT NULL", name="ck_notes_content_latex_required"
        ),
        sa.CheckConstraint("status <> ''", name="ck_notes_status_non_empty"),
    )
    op.create_index("ix_notes_library_item_id", "notes", ["library_item_id"])
    op.create_index("ix_notes_status", "notes", ["status"])
    op.create_index("ix_notes_created_at", "notes", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notes_created_at", table_name="notes")
    op.drop_index("ix_notes_status", table_name="notes")
    op.drop_index("ix_notes_library_item_id", table_name="notes")
    op.drop_table("notes")
