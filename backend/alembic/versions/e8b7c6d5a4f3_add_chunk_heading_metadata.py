"""add chunk heading metadata

Revision ID: e8b7c6d5a4f3
Revises: c2f4b8a19d37
Create Date: 2026-07-08 19:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b7c6d5a4f3"
down_revision: Union[str, None] = "c2f4b8a19d37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("document_chunks", sa.Column("chapter_title", sa.String(), nullable=True))
    op.add_column("document_chunks", sa.Column("section_title", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_chunks", "section_title")
    op.drop_column("document_chunks", "chapter_title")
