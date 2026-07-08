"""add section type to document chunks

Revision ID: c2f4b8a19d37
Revises: 9d4a6f1b2c30
Create Date: 2026-07-08 18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f4b8a19d37"
down_revision: Union[str, None] = "9d4a6f1b2c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "document_chunks",
        sa.Column(
            "section_type",
            sa.String(),
            server_default="unknown",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_chunks", "section_type")
