"""add pgvector extension and embedding column to document_chunks

Revision ID: d9b287f324f9
Revises: ff156aef8dbe
Create Date: 2026-07-05 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9b287f324f9"
down_revision: Union[str, None] = "ff156aef8dbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Historical Stage 4 embedding dimension. Do not import mutable app
# constants (e.g. app.embeddings.base.EMBEDDING_DIMENSION) in migrations:
# migrations are immutable historical snapshots, and if the app constant
# changes later, replaying this migration must still produce the exact
# schema that was created at this revision.
STAGE_4_EMBEDDING_DIMENSION = 16


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(STAGE_4_EMBEDDING_DIMENSION), nullable=True),
    )
    # No index added in Stage 4: pgvector indexes (ivfflat/hnsw) need
    # careful tuning against real data volume. Tracked as future work.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_chunks", "embedding")
    # Intentionally not dropping the "vector" extension: other future
    # tables may depend on it.
