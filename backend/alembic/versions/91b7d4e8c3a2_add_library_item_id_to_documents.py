"""add library item relationship to documents

Revision ID: 91b7d4e8c3a2
Revises: 8c2f7d6a9b41
Create Date: 2026-07-06 14:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91b7d4e8c3a2"
down_revision: Union[str, None] = "8c2f7d6a9b41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents",
        sa.Column("library_item_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_library_item_id_library_items",
        "documents",
        "library_items",
        ["library_item_id"],
        ["id"],
    )
    op.create_index(
        "ix_documents_library_item_id", "documents", ["library_item_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_documents_library_item_id", table_name="documents")
    op.drop_constraint(
        "fk_documents_library_item_id_library_items", "documents", type_="foreignkey"
    )
    op.drop_column("documents", "library_item_id")
