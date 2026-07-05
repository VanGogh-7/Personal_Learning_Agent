"""add library_items table for book library MVP

Revision ID: 8c2f7d6a9b41
Revises: 4fe6d409baff
Create Date: 2026-07-06 10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c2f7d6a9b41"
down_revision: Union[str, None] = "4fe6d409baff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "library_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("file_type", sa.String(), nullable=True),
        sa.Column("topic_tags", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="registered"),
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
        sa.CheckConstraint("title <> ''", name="ck_library_items_title_non_empty"),
        sa.CheckConstraint("status <> ''", name="ck_library_items_status_non_empty"),
    )
    op.create_index("ix_library_items_title", "library_items", ["title"])
    op.create_index("ix_library_items_status", "library_items", ["status"])
    op.create_index("ix_library_items_created_at", "library_items", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_library_items_created_at", table_name="library_items")
    op.drop_index("ix_library_items_status", table_name="library_items")
    op.drop_index("ix_library_items_title", table_name="library_items")
    op.drop_table("library_items")
