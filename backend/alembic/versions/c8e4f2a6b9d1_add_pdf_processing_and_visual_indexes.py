"""Add versioned legacy-PDF processing and visual experiment tables.

Revision ID: c8e4f2a6b9d1
Revises: f3a9c1d7e5b2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e4f2a6b9d1"
down_revision: str | None = "f3a9c1d7e5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pdf_processing_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("pdf_type", sa.String(length=32), nullable=False),
        sa.Column("detection_evidence", sa.JSON(), nullable=False),
        sa.Column("parser_name", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("ocr_engine", sa.String(length=80), nullable=True),
        sa.Column("ocr_version", sa.String(length=80), nullable=True),
        sa.Column("text_index_version_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("error_category", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["text_index_version_id"], ["embedding_index_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pdf_processing_versions_document_id",
        "pdf_processing_versions",
        ["document_id"],
    )
    op.add_column(
        "documents", sa.Column("active_processing_version_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_documents_active_processing_version",
        "documents",
        "pdf_processing_versions",
        ["active_processing_version_id"],
        ["id"],
    )
    op.create_table(
        "document_pages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("processing_version_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("bounding_boxes", sa.JSON(), nullable=False),
        sa.Column("text_character_count", sa.Integer(), nullable=False),
        sa.Column("image_coverage_ratio", sa.Float(), nullable=False),
        sa.Column("width_points", sa.Float(), nullable=True),
        sa.Column("height_points", sa.Float(), nullable=True),
        sa.Column("page_checksum", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["processing_version_id"],
            ["pdf_processing_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "processing_version_id",
            "page_number",
            name="uq_document_pages_version_page",
        ),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_index(
        "ix_document_pages_processing_version_id",
        "document_pages",
        ["processing_version_id"],
    )
    op.add_column(
        "document_chunks", sa.Column("processing_version_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "document_chunks", sa.Column("parent_chunk_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "element_type",
            sa.String(length=40),
            server_default="paragraph",
            nullable=False,
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("section_path", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "document_chunks",
        sa.Column("bounding_boxes", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "extraction_method",
            sa.String(length=40),
            server_default="text",
            nullable=False,
        ),
    )
    op.add_column(
        "document_chunks", sa.Column("ocr_confidence", sa.Float(), nullable=True)
    )
    op.create_foreign_key(
        "fk_document_chunks_processing_version",
        "document_chunks",
        "pdf_processing_versions",
        ["processing_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_document_chunks_parent",
        "document_chunks",
        "document_chunks",
        ["parent_chunk_id"],
        ["id"],
    )
    op.create_index(
        "ix_document_chunks_processing_version_id",
        "document_chunks",
        ["processing_version_id"],
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_fts_simple ON document_chunks USING gin "
        "(to_tsvector('simple'::regconfig, "
        "COALESCE(chapter_title, '') || ' ' || "
        "COALESCE(section_title, '') || ' ' || content))"
    )
    op.drop_constraint(
        "uq_document_chunks_document_id_chunk_index", "document_chunks", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_version_chunk_index",
        "document_chunks",
        ["document_id", "processing_version_id", "chunk_index"],
    )
    op.create_table(
        "visual_index_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("processing_version_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("index_format", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("storage_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["processing_version_id"],
            ["pdf_processing_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_index_versions_processing_version_id",
        "visual_index_versions",
        ["processing_version_id"],
    )
    op.create_table(
        "visual_page_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("visual_index_version_id", sa.UUID(), nullable=False),
        sa.Column("document_page_id", sa.UUID(), nullable=False),
        sa.Column("page_version", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("storage_bytes", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_page_id"], ["document_pages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["visual_index_version_id"],
            ["visual_index_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "visual_index_version_id",
            "document_page_id",
            name="uq_visual_page_embeddings_version_page",
        ),
    )
    op.create_index(
        "ix_visual_page_embeddings_visual_index_version_id",
        "visual_page_embeddings",
        ["visual_index_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_visual_page_embeddings_visual_index_version_id",
        table_name="visual_page_embeddings",
    )
    op.drop_table("visual_page_embeddings")
    op.drop_index(
        "ix_visual_index_versions_processing_version_id",
        table_name="visual_index_versions",
    )
    op.drop_table("visual_index_versions")
    op.drop_constraint(
        "uq_document_chunks_document_version_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_id_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts_simple")
    op.drop_index(
        "ix_document_chunks_processing_version_id", table_name="document_chunks"
    )
    op.drop_constraint(
        "fk_document_chunks_parent", "document_chunks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_document_chunks_processing_version", "document_chunks", type_="foreignkey"
    )
    for column in (
        "ocr_confidence",
        "extraction_method",
        "bounding_boxes",
        "section_path",
        "element_type",
        "parent_chunk_id",
        "processing_version_id",
    ):
        op.drop_column("document_chunks", column)
    op.drop_index(
        "ix_document_pages_processing_version_id", table_name="document_pages"
    )
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_constraint(
        "fk_documents_active_processing_version", "documents", type_="foreignkey"
    )
    op.drop_column("documents", "active_processing_version_id")
    op.drop_index(
        "ix_pdf_processing_versions_document_id", table_name="pdf_processing_versions"
    )
    op.drop_table("pdf_processing_versions")
