"""Add isolated 1024-dimensional embedding storage and HNSW indexes.

Revision ID: e5c8a1f4b2d9
Revises: d4b7e2a9c6f1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "e5c8a1f4b2d9"
down_revision: str | None = "d4b7e2a9c6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHUNK_HNSW_INDEX = "ix_chunk_embeddings_embedding_1024_hnsw"
LEGACY_HNSW_INDEX = "ix_document_chunks_embedding_1024_hnsw"


def upgrade() -> None:
    # Preserve every old 2048-dimensional value. New writes use separate,
    # fixed-width vector(1024) columns; there is no cast or truncation.
    op.alter_column(
        "document_chunks",
        "embedding",
        new_column_name="embedding_2048",
        existing_type=Vector(2048),
        existing_nullable=True,
    )
    op.add_column(
        "document_chunks", sa.Column("embedding", Vector(1024), nullable=True)
    )
    op.alter_column(
        "chunk_embeddings",
        "embedding",
        new_column_name="embedding_legacy",
        existing_type=Vector(),
        existing_nullable=False,
    )
    op.add_column(
        "chunk_embeddings", sa.Column("embedding", Vector(1024), nullable=True)
    )
    op.alter_column(
        "long_term_memories",
        "embedding",
        new_column_name="embedding_2048",
        existing_type=Vector(2048),
        existing_nullable=True,
    )
    op.add_column(
        "long_term_memories", sa.Column("embedding", Vector(1024), nullable=True)
    )

    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_embedding_index_versions_profile_status",
        "embedding_index_versions",
        ["embedding_profile_id", "status"],
    )
    # pgvector defaults (m=16, ef_construction=64) are intentionally retained
    # until the Stage 64D benchmark demonstrates a reason to tune them.
    op.execute(
        sa.text(
            f"CREATE INDEX {CHUNK_HNSW_INDEX} ON chunk_embeddings "
            "USING hnsw (embedding vector_l2_ops) WHERE embedding IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX {LEGACY_HNSW_INDEX} ON document_chunks "
            "USING hnsw (embedding vector_l2_ops) WHERE embedding IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {LEGACY_HNSW_INDEX}"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {CHUNK_HNSW_INDEX}"))
    op.drop_index(
        "ix_embedding_index_versions_profile_status",
        table_name="embedding_index_versions",
    )
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")

    # Old application code cannot consume a 1024 profile. Preserve its
    # non-secret metadata, but make it inactive and remove only the incompatible
    # new vectors before restoring the 2048 schema.
    op.execute(
        sa.text(
            "UPDATE pdf_processing_versions SET text_index_version_id = NULL "
            "WHERE text_index_version_id IN "
            "(SELECT id FROM embedding_index_versions WHERE dimension = 1024)"
        )
    )
    op.execute(sa.text("DELETE FROM chunk_embeddings WHERE embedding IS NOT NULL"))
    op.execute(
        sa.text(
            "UPDATE embedding_index_versions SET status = 'failed' "
            "WHERE dimension = 1024"
        )
    )
    op.execute(
        sa.text(
            "UPDATE provider_profiles SET is_active = false "
            "WHERE kind = 'embedding' AND embedding_dimension = 1024"
        )
    )

    op.drop_column("long_term_memories", "embedding")
    op.alter_column(
        "long_term_memories",
        "embedding_2048",
        new_column_name="embedding",
        existing_type=Vector(2048),
        existing_nullable=True,
    )
    op.drop_column("chunk_embeddings", "embedding")
    op.alter_column(
        "chunk_embeddings",
        "embedding_legacy",
        new_column_name="embedding",
        existing_type=Vector(),
        existing_nullable=True,
    )
    op.alter_column("chunk_embeddings", "embedding", nullable=False)
    op.drop_column("document_chunks", "embedding")
    op.alter_column(
        "document_chunks",
        "embedding_2048",
        new_column_name="embedding",
        existing_type=Vector(2048),
        existing_nullable=True,
    )
