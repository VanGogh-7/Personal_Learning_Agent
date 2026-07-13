"""Allow 1024 rows to omit the preserved legacy vector.

Revision ID: f6d9b2c5a8e1
Revises: e5c8a1f4b2d9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "f6d9b2c5a8e1"
down_revision: str | None = "e5c8a1f4b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "chunk_embeddings",
        "embedding_legacy",
        existing_type=Vector(),
        nullable=True,
    )


def downgrade() -> None:
    # Rows created in the new fixed-width space cannot satisfy the former
    # legacy NOT NULL contract. Remove only those incompatible rows; the next
    # downgrade revision removes/deactivates their 1024 index versions.
    op.execute(sa.text("DELETE FROM chunk_embeddings WHERE embedding_legacy IS NULL"))
    op.alter_column(
        "chunk_embeddings",
        "embedding_legacy",
        existing_type=Vector(),
        nullable=False,
    )
