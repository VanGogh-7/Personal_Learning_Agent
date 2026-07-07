"""Index one local PDF through the backend PDF-to-RAG pipeline."""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.embeddings.providers import get_embedding_provider
from app.ingestion.pdf import PDFExtractionError, extract_pdf_pages
from app.library.indexing import LibraryIndexingError, index_library_item
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem


@dataclass(frozen=True)
class IndexPdfSummary:
    library_item_id: uuid.UUID
    document_id: uuid.UUID
    chunk_count: int
    embedding_provider: str
    embedding_dimension: int
    empty_page_count: int


def index_pdf_file(pdf_path: str | Path, session: Session | None = None) -> IndexPdfSummary:
    """Create or reuse a Library item and index its PDF content."""
    path = _validate_pdf_path(pdf_path)
    owns_session = session is None
    db = session or get_db_session()

    try:
        pages = extract_pdf_pages(path)
        empty_page_count = sum(1 for page in pages if not page.text.strip())

        item = _get_or_create_library_item(db, path)
        provider = get_embedding_provider()
        result = index_library_item(db, item.id, embedding_provider=provider)
        if result is None or result.document_id is None:
            raise LibraryIndexingError("PDF indexing did not produce a document record.")

        chunk_count = db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == result.document_id
            )
        )
        if owns_session:
            db.commit()

        return IndexPdfSummary(
            library_item_id=item.id,
            document_id=result.document_id,
            chunk_count=int(chunk_count or 0),
            embedding_provider=provider.provider_name,
            embedding_dimension=provider.dimension,
            empty_page_count=empty_page_count,
        )
    except Exception:
        if owns_session:
            db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _validate_pdf_path(pdf_path: str | Path) -> Path:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise LibraryIndexingError(f"PDF file does not exist: {path}")
    if not path.is_file():
        raise LibraryIndexingError(f"PDF path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise LibraryIndexingError("Only .pdf files can be indexed by this script.")
    return path


def _get_or_create_library_item(session: Session, path: Path) -> LibraryItem:
    existing = session.execute(
        select(LibraryItem).where(LibraryItem.file_path == str(path)).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        existing.title = existing.title or path.stem
        existing.file_type = "pdf"
        existing.file_path = str(path)
        session.flush()
        return existing

    item = LibraryItem(
        title=path.stem,
        file_path=str(path),
        file_type="pdf",
        status="registered",
    )
    session.add(item)
    session.flush()
    return item


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index one local PDF into the Personal Learning Agent backend."
    )
    parser.add_argument("pdf_path", help="Path to the local .pdf file to index.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        summary = index_pdf_file(args.pdf_path)
    except (LibraryIndexingError, PDFExtractionError, ValueError) as exc:
        print(f"Indexing failed: {exc}", file=sys.stderr)
        return 1

    print("PDF indexed successfully.")
    print(f"library_item_id: {summary.library_item_id}")
    print(f"document_id: {summary.document_id}")
    print(f"chunk_count: {summary.chunk_count}")
    print(f"embedding_provider: {summary.embedding_provider}")
    print(f"embedding_dimension: {summary.embedding_dimension}")
    print(f"empty_page_count: {summary.empty_page_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
