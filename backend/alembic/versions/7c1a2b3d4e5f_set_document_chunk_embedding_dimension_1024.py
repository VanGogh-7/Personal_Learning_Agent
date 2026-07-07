"""set document chunk embedding dimension to 1024

Revision ID: 7c1a2b3d4e5f
Revises: 2f8c3a7d9e10
Create Date: 2026-07-08 10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1a2b3d4e5f"
down_revision: Union[str, None] = "2f8c3a7d9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_EMBEDDING_DIMENSION = 16
ZHIPU_EMBEDDING_DIMENSION = 1024


def upgrade() -> None:
    """Upgrade schema."""
    # Existing deterministic/mock embeddings are 16-dimensional and cannot
    # be cast into vector(1024). Clear them before changing the column type;
    # affected documents can be re-indexed with the configured provider.
    op.execute("UPDATE document_chunks SET embedding = NULL WHERE embedding IS NOT NULL")
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=Vector(OLD_EMBEDDING_DIMENSION),
        type_=Vector(ZHIPU_EMBEDDING_DIMENSION),
        nullable=True,
        postgresql_using=f"NULL::vector({ZHIPU_EMBEDDING_DIMENSION})",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE document_chunks SET embedding = NULL WHERE embedding IS NOT NULL")
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=Vector(ZHIPU_EMBEDDING_DIMENSION),
        type_=Vector(OLD_EMBEDDING_DIMENSION),
        nullable=True,
        postgresql_using=f"NULL::vector({OLD_EMBEDDING_DIMENSION})",
    )
