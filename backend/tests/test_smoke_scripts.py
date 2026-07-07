from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from scripts.ask_book import ask_book
from scripts.index_pdf import index_pdf_file
from tests.pdf_fixtures import make_pdf_bytes


def _create_script_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    LibraryItem.metadata.create_all(
        engine,
        tables=[LibraryItem.__table__, Document.__table__, DocumentChunk.__table__],
    )
    session = Session(engine)
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


def _close_script_session(session: Session) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    session.close()
    engine.dispose()


def test_index_pdf_script_indexes_pdf_and_preserves_page_metadata(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "Complete metric spaces are central in analysis.",
                    "",
                    "Banach spaces are complete normed vector spaces.",
                ]
            )
        )

        summary = index_pdf_file(pdf_path, session=session)

        assert summary.chunk_count == 2
        assert summary.embedding_provider == "mock"
        assert summary.embedding_dimension == EMBEDDING_DIMENSION
        assert summary.empty_page_count == 1

        item = session.get(LibraryItem, summary.library_item_id)
        assert item is not None
        assert item.file_type == "pdf"
        assert item.status == "indexed"

        document = session.get(Document, summary.document_id)
        assert document is not None
        assert document.library_item_id == summary.library_item_id
        assert document.file_path == str(pdf_path.resolve())

        chunks = session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == summary.document_id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars().all()
        assert [chunk.page_start for chunk in chunks] == [1, 3]
        assert [chunk.page_end for chunk in chunks] == [1, 3]
        assert all(chunk.embedding is not None for chunk in chunks)
        assert all(len(chunk.embedding) == EMBEDDING_DIMENSION for chunk in chunks)
    finally:
        _close_script_session(session)


def test_index_pdf_script_reuses_library_item_for_same_path(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(make_pdf_bytes(["Compactness has many equivalent forms."]))

        first = index_pdf_file(pdf_path, session=session)
        second = index_pdf_file(pdf_path, session=session)

        assert second.library_item_id == first.library_item_id
        assert second.document_id == first.document_id
        items = session.execute(select(LibraryItem)).scalars().all()
        assert len(items) == 1
    finally:
        _close_script_session(session)


def test_ask_book_script_runs_single_book_rag_with_citations(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "functional-analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "A Banach space is a complete normed vector space.",
                    "A complete metric space is one where every Cauchy sequence converges.",
                ]
            )
        )
        indexed = index_pdf_file(pdf_path, session=session)

        summary = ask_book(
            "What does the book say about Banach spaces?",
            library_item_id=indexed.library_item_id,
            top_k=2,
            session=session,
        )

        assert summary.library_item_id == indexed.library_item_id
        assert summary.answer
        assert len(summary.citations) == 2
        assert {citation.library_item_id for citation in summary.citations} == {
            str(indexed.library_item_id)
        }
        assert {citation.document_id for citation in summary.citations} == {
            str(indexed.document_id)
        }
        assert {citation.page_number for citation in summary.citations} == {1, 2}
        assert all(citation.excerpt for citation in summary.citations)
    finally:
        _close_script_session(session)
