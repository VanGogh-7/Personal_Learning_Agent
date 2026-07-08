"""set document chunk embedding dimension to 2048

Revision ID: 9d4a6f1b2c30
Revises: 7c1a2b3d4e5f
Create Date: 2026-07-08 16:00:00

"""
from typing import Sequence, Union

from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4a6f1b2c30"
down_revision: Union[str, None] = "7c1a2b3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_EMBEDDING_DIMENSION = 1024
ZHIPU_EMBEDDING_DIMENSION = 2048


def upgrade() -> None:
    """Upgrade schema."""
    # Existing 1024-dimensional vectors cannot be cast into vector(2048).
    # Keep documents and Library items, but remove chunks before changing type.
    op.execute("DELETE FROM document_chunks")
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
    op.execute("DELETE FROM document_chunks")
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=Vector(ZHIPU_EMBEDDING_DIMENSION),
        type_=Vector(OLD_EMBEDDING_DIMENSION),
        nullable=True,
        postgresql_using=f"NULL::vector({OLD_EMBEDDING_DIMENSION})",
    )
