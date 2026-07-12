"""Add Provider profiles and versioned embedding spaces.

Revision ID: f3a9c1d7e5b2
Revises: a1c4e7f9b2d6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "f3a9c1d7e5b2"
down_revision: str | None = "a1c4e7f9b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("secret_ref", sa.String(length=200), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("extra_headers", sa.JSON(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_profiles_kind", "provider_profiles", ["kind"])
    op.create_table(
        "embedding_index_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("embedding_profile_id", sa.UUID(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("embedded_chunks", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["embedding_profile_id"], ["provider_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_embedding_index_versions_embedding_profile_id",
        "embedding_index_versions",
        ["embedding_profile_id"],
    )
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("index_version_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["embedding_index_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id", "index_version_id", name="uq_chunk_embeddings_chunk_version"
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_index_version_id",
        "chunk_embeddings",
        ["index_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_embeddings_index_version_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.drop_index(
        "ix_embedding_index_versions_embedding_profile_id",
        table_name="embedding_index_versions",
    )
    op.drop_table("embedding_index_versions")
    op.drop_index("ix_provider_profiles_kind", table_name="provider_profiles")
    op.drop_table("provider_profiles")
