"""add long_term_memories table for long-term memory MVP

Revision ID: 4fe6d409baff
Revises: ffbb0aa351cd
Create Date: 2026-07-05 14:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4fe6d409baff"
down_revision: Union[str, None] = "ffbb0aa351cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "long_term_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "memory_type <> ''", name="ck_long_term_memories_memory_type_non_empty"
        ),
        sa.CheckConstraint("content <> ''", name="ck_long_term_memories_content_non_empty"),
        sa.CheckConstraint(
            "importance >= 1 AND importance <= 5", name="ck_long_term_memories_importance_range"
        ),
    )
    op.create_index(
        "ix_long_term_memories_memory_type", "long_term_memories", ["memory_type"]
    )
    op.create_index(
        "ix_long_term_memories_importance", "long_term_memories", ["importance"]
    )
    op.create_index(
        "ix_long_term_memories_created_at", "long_term_memories", ["created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_long_term_memories_created_at", table_name="long_term_memories")
    op.drop_index("ix_long_term_memories_importance", table_name="long_term_memories")
    op.drop_index("ix_long_term_memories_memory_type", table_name="long_term_memories")
    op.drop_table("long_term_memories")
