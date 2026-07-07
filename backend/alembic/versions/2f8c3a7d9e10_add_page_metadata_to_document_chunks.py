"""add page metadata to document chunks

Revision ID: 2f8c3a7d9e10
Revises: 6a8c3d4e5f01
Create Date: 2026-07-07 20:40:00

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f8c3a7d9e10"
down_revision: Union[str, None] = "6a8c3d4e5f01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("document_chunks", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("page_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_chunks", "page_end")
    op.drop_column("document_chunks", "page_start")
