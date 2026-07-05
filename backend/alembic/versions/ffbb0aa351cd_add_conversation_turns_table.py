"""add conversation_turns table for short-term memory

Revision ID: ffbb0aa351cd
Revises: d9b287f324f9
Create Date: 2026-07-05 13:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ffbb0aa351cd"
down_revision: Union[str, None] = "d9b287f324f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("session_id <> ''", name="ck_conversation_turns_session_id_non_empty"),
        sa.CheckConstraint("question <> ''", name="ck_conversation_turns_question_non_empty"),
        sa.CheckConstraint("answer <> ''", name="ck_conversation_turns_answer_non_empty"),
    )
    op.create_index(
        "ix_conversation_turns_session_id", "conversation_turns", ["session_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_conversation_turns_session_id", table_name="conversation_turns")
    op.drop_table("conversation_turns")
