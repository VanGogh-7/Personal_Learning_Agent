"""Restore legacy document chunk uniqueness for null processing versions.

Revision ID: d4b7e2a9c6f1
Revises: c8e4f2a6b9d1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4b7e2a9c6f1"
down_revision: str | None = "c8e4f2a6b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_document_chunks_legacy_document_chunk_index"


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT document_id, chunk_index, COUNT(*) AS duplicate_count "
                "FROM document_chunks "
                "WHERE processing_version_id IS NULL "
                "GROUP BY document_id, chunk_index "
                "HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(
            "Cannot restore legacy chunk uniqueness: duplicate null-version "
            "document chunks exist. Resolve duplicates before retrying the migration."
        )
    op.create_index(
        INDEX_NAME,
        "document_chunks",
        ["document_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("processing_version_id IS NULL"),
        sqlite_where=sa.text("processing_version_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="document_chunks")
