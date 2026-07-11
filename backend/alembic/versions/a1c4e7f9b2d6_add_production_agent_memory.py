"""add production agent memory architecture

Revision ID: a1c4e7f9b2d6
Revises: e8b7c6d5a4f3
Create Date: 2026-07-11 12:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "a1c4e7f9b2d6"
down_revision: Union[str, None] = "e8b7c6d5a4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSION = 2048


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column(
            "namespace", sa.String(), server_default="default_user", nullable=False
        ),
        sa.Column("subject_id", sa.String(), nullable=True),
        sa.Column("legacy_session_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_session_id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        "ix_conversations_namespace_subject",
        "conversations",
        ["namespace", "subject_id"],
    )

    op.add_column(
        "conversation_turns", sa.Column("conversation_id", sa.UUID(), nullable=True)
    )
    op.execute(
        """
        INSERT INTO conversations (id, thread_id, namespace, legacy_session_id)
        SELECT md5('pla-conversation:' || session_id)::uuid,
               'legacy:' || session_id,
               'default_user',
               session_id
        FROM conversation_turns
        GROUP BY session_id
        """
    )
    op.execute(
        """
        UPDATE conversation_turns AS turn
        SET conversation_id = conversation.id
        FROM conversations AS conversation
        WHERE conversation.legacy_session_id = turn.session_id
        """
    )
    op.create_foreign_key(
        "fk_conversation_turns_conversation_id",
        "conversation_turns",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_conversation_turns_conversation_id",
        "conversation_turns",
        ["conversation_id"],
    )

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("covered_until_turn_id", sa.UUID(), nullable=False),
        sa.Column("source_turn_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["covered_until_turn_id"], ["conversation_turns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", name="uq_conversation_summaries_conversation_id"
        ),
    )
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
    )

    op.add_column(
        "long_term_memories",
        sa.Column(
            "namespace", sa.String(), server_default="default_user", nullable=False
        ),
    )
    op.add_column(
        "long_term_memories", sa.Column("subject_id", sa.String(), nullable=True)
    )
    op.add_column(
        "long_term_memories", sa.Column("memory_subtype", sa.String(), nullable=True)
    )
    op.add_column(
        "long_term_memories", sa.Column("structured_data", sa.JSON(), nullable=True)
    )
    op.alter_column(
        "long_term_memories",
        "structured_data",
        type_=JSONB(),
        existing_type=sa.JSON(),
        postgresql_using="structured_data::jsonb",
    )
    op.add_column(
        "long_term_memories",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
    )
    op.add_column(
        "long_term_memories",
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
    )
    op.add_column(
        "long_term_memories",
        sa.Column("status", sa.String(), server_default="active", nullable=False),
    )
    op.add_column(
        "long_term_memories", sa.Column("source_type", sa.String(), nullable=True)
    )
    op.add_column(
        "long_term_memories", sa.Column("source_turn_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "long_term_memories", sa.Column("source_event_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "long_term_memories", sa.Column("supersedes_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "long_term_memories",
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "long_term_memories",
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "long_term_memories",
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE long_term_memories SET source_type = source WHERE source_type IS NULL"
    )
    op.create_foreign_key(
        "fk_long_term_memories_source_turn_id",
        "long_term_memories",
        "conversation_turns",
        ["source_turn_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_long_term_memories_source_event_id",
        "long_term_memories",
        "learning_events",
        ["source_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_long_term_memories_supersedes_id",
        "long_term_memories",
        "long_term_memories",
        ["supersedes_id"],
        ["id"],
    )
    op.create_index(
        "ix_long_term_memories_namespace_status",
        "long_term_memories",
        ["namespace", "status"],
    )
    op.create_index(
        "ix_long_term_memories_type_subtype",
        "long_term_memories",
        ["memory_type", "memory_subtype"],
    )


def downgrade() -> None:
    op.drop_index("ix_long_term_memories_type_subtype", table_name="long_term_memories")
    op.drop_index(
        "ix_long_term_memories_namespace_status", table_name="long_term_memories"
    )
    op.drop_constraint(
        "fk_long_term_memories_supersedes_id", "long_term_memories", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_long_term_memories_source_event_id",
        "long_term_memories",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_long_term_memories_source_turn_id", "long_term_memories", type_="foreignkey"
    )
    for column in (
        "access_count",
        "valid_until",
        "valid_from",
        "supersedes_id",
        "source_event_id",
        "source_turn_id",
        "source_type",
        "status",
        "confidence",
        "embedding",
        "structured_data",
        "memory_subtype",
        "subject_id",
        "namespace",
    ):
        op.drop_column("long_term_memories", column)

    op.drop_index(
        "ix_conversation_summaries_conversation_id", table_name="conversation_summaries"
    )
    op.drop_table("conversation_summaries")
    op.drop_index(
        "ix_conversation_turns_conversation_id", table_name="conversation_turns"
    )
    op.drop_constraint(
        "fk_conversation_turns_conversation_id",
        "conversation_turns",
        type_="foreignkey",
    )
    op.drop_column("conversation_turns", "conversation_id")
    op.drop_index("ix_conversations_namespace_subject", table_name="conversations")
    op.drop_table("conversations")
