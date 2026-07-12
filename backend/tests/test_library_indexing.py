import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.embeddings.base import EMBEDDING_DIMENSION
from app.library.service import create_library_item
from app.library.indexing import (
    LibraryIndexingError,
    classify_pdf_section_type,
    detect_pdf_heading_context,
    index_library_item,
)
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from app.models.pdf_processing import DocumentPage, PdfProcessingVersion
from tests.pdf_fixtures import make_pdf_bytes


@pytest.fixture
def indexing_session():
    engine = create_engine("sqlite:///:memory:")
    LibraryItem.metadata.create_all(
        engine,
        tables=[
            LibraryItem.__table__,
            Document.__table__,
            PdfProcessingVersion.__table__,
            DocumentPage.__table__,
            DocumentChunk.__table__,
        ],
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_index_library_item_txt_creates_document_chunks_and_embeddings(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "linear-algebra.txt"
    file_path.write_text("Vector spaces are central.\n" * 80, encoding="utf-8")
    item = create_library_item(
        indexing_session,
        title="Linear Algebra",
        file_path=str(file_path),
        file_type="txt",
    )

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    assert result.status == "indexed"
    assert result.chunks_created > 0
    assert result.embeddings_created == result.chunks_created

    document = indexing_session.get(Document, result.document_id)
    assert document is not None
    assert document.library_item_id == item.item_id
    assert document.title == "Linear Algebra"
    assert document.file_type == "txt"
    assert document.content_hash

    chunks = (
        indexing_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        .scalars()
        .all()
    )
    assert len(chunks) == result.chunks_created
    assert all(chunk.embedding is not None for chunk in chunks)
    assert all(len(chunk.embedding) == EMBEDDING_DIMENSION for chunk in chunks)

    updated_item = indexing_session.get(LibraryItem, item.item_id)
    assert updated_item is not None
    assert updated_item.status == "indexed"


def test_index_library_item_md_succeeds(indexing_session, tmp_path) -> None:
    file_path = tmp_path / "topology.md"
    file_path.write_text(
        "# Topology\n\nOpen sets and compactness.\n" * 20, encoding="utf-8"
    )
    item = create_library_item(
        indexing_session,
        title="Topology Notes",
        file_path=str(file_path),
        file_type="md",
    )

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    assert result.status == "indexed"
    assert result.chunks_created > 0


def test_index_library_item_missing_id_returns_none(indexing_session) -> None:
    assert index_library_item(indexing_session, uuid.uuid4()) is None


def test_index_library_item_empty_file_path_sets_failed_status(
    indexing_session,
) -> None:
    item = create_library_item(indexing_session, title="No File")

    with pytest.raises(LibraryIndexingError, match="no local file path"):
        index_library_item(indexing_session, item.item_id)

    updated_item = indexing_session.get(LibraryItem, item.item_id)
    assert updated_item is not None
    assert updated_item.status == "index_failed"


def test_index_library_item_pdf_creates_page_aware_chunks(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "analysis.pdf"
    file_path.write_bytes(
        make_pdf_bytes(
            [
                "Derivatives measure local linear change.",
                "Integrals accumulate area under curves.",
            ]
        )
    )
    item = create_library_item(
        indexing_session,
        title="Analysis",
        file_path=str(file_path),
        file_type="pdf",
    )

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    assert result.status == "indexed"
    document = indexing_session.get(Document, result.document_id)
    assert document is not None
    assert document.file_type == "pdf"
    chunks = (
        indexing_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        )
        .scalars()
        .all()
    )
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
    assert chunks[0].section_type == "body"
    assert "Derivatives measure local linear change." in chunks[0].content
    assert "Integrals accumulate area under curves." in chunks[0].content


def test_index_library_item_pdf_strips_nul_bytes_before_storage(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "analysis.pdf"
    file_path.write_bytes(make_pdf_bytes(["Metric\x00 spaces contain open balls."]))
    item = create_library_item(
        indexing_session,
        title="Analysis",
        file_path=str(file_path),
        file_type="pdf",
    )

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    chunks = (
        indexing_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == result.document_id)
        )
        .scalars()
        .all()
    )
    assert [chunk.content for chunk in chunks] == ["Metric spaces contain open balls."]


def test_index_library_item_pdf_classifies_non_body_sections(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "analysis.pdf"
    file_path.write_bytes(
        make_pdf_bytes(
            [
                "Contents Chapter I Foundations 3 Chapter II Convergence 131",
                "Preface This book grew from a series of lectures.",
                "I.1 Fundamentals of Logic A statement is either true or false.",
                "Index Banach space 176 compact 250 metric 401",
                "Index normed vector 148 open set 232 topology 317",
            ]
        )
    )
    item = create_library_item(
        indexing_session,
        title="Analysis",
        file_path=str(file_path),
        file_type="pdf",
    )

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    chunks = (
        indexing_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == result.document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        .scalars()
        .all()
    )
    assert [chunk.section_type for chunk in chunks] == [
        "contents",
        "preface",
        "body",
        "index",
    ]
    index_chunk = chunks[-1]
    assert index_chunk.page_start == 4
    assert index_chunk.page_end == 5
    assert "Banach space" in index_chunk.content
    assert "normed vector" in index_chunk.content


def test_index_library_item_pdf_uses_larger_multi_page_chunks(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "analysis.pdf"
    item = create_library_item(
        indexing_session,
        title="Analysis",
        file_path=str(file_path),
        file_type="pdf",
    )
    page_texts = [
        f"II.6 Completeness\n{'Complete metric spaces and Cauchy sequences. ' * 35}",
        f"{'Banach spaces are complete normed vector spaces. ' * 35}",
        f"{'Convergent sequences are Cauchy in metric spaces. ' * 35}",
        f"{'Closed subspaces of Banach spaces are complete. ' * 35}",
    ]
    file_path.write_bytes(make_pdf_bytes(page_texts))

    result = index_library_item(indexing_session, item.item_id)

    assert result is not None
    chunks = (
        indexing_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == result.document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        .scalars()
        .all()
    )
    assert len(chunks) < len(page_texts)
    assert chunks[0].page_start == 1
    assert chunks[0].page_end is not None
    assert chunks[0].page_end > 1
    assert chunks[0].section_title == "II.6 Completeness"
    assert all(len(chunk.content) >= 350 for chunk in chunks)


def test_classify_pdf_section_type_uses_lightweight_heuristics() -> None:
    assert (
        classify_pdf_section_type("Contents\nChapter I Foundations .... 3")
        == "contents"
    )
    assert classify_pdf_section_type("x Contents\n6 Countability .... 46") == "contents"
    assert classify_pdf_section_type("Index 421\nBanach space, 176") == "index"
    assert (
        classify_pdf_section_type("Bibliography\n[1] Some reference") == "bibliography"
    )
    assert classify_pdf_section_type("Preface\nThis book...") == "preface"
    assert (
        classify_pdf_section_type("II.6 Completeness\nA metric space is...") == "body"
    )


def test_detect_pdf_heading_context_uses_obvious_chapter_and_section_headings() -> None:
    assert detect_pdf_heading_context(
        "Chapter II Convergence\nSequences"
    ).chapter_title == ("Chapter II Convergence")
    assert (
        detect_pdf_heading_context("12 I Foundations").chapter_title == "I Foundations"
    )
    context = detect_pdf_heading_context("II.6 Completeness 177\nA metric space is...")
    assert context.section_title == "II.6 Completeness"
    header_context = detect_pdf_heading_context(
        "338 IV Differentiation in One Variable 3 Taylor's Theorem"
    )
    assert header_context.chapter_title == "IV Differentiation in One Variable"
    assert header_context.section_title == "IV.3 Taylor's Theorem"


def test_index_library_item_invalid_pdf_sets_failed_status(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "broken.pdf"
    file_path.write_text("not really a pdf", encoding="utf-8")
    item = create_library_item(
        indexing_session,
        title="Broken PDF",
        file_path=str(file_path),
        file_type="pdf",
    )

    with pytest.raises(LibraryIndexingError, match="Could not read PDF file"):
        index_library_item(indexing_session, item.item_id)

    updated_item = indexing_session.get(LibraryItem, item.item_id)
    assert updated_item is not None
    assert updated_item.status == "index_failed"


def test_index_library_item_rejects_nonexistent_file(
    indexing_session, tmp_path
) -> None:
    item = create_library_item(
        indexing_session,
        title="Missing",
        file_path=str(tmp_path / "missing.txt"),
        file_type="txt",
    )

    with pytest.raises(LibraryIndexingError, match="does not exist"):
        index_library_item(indexing_session, item.item_id)


def test_reindex_library_item_replaces_existing_chunks(
    indexing_session, tmp_path
) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("first version\n" * 120, encoding="utf-8")
    item = create_library_item(
        indexing_session,
        title="Notes",
        file_path=str(file_path),
        file_type="txt",
    )
    first = index_library_item(indexing_session, item.item_id)
    assert first is not None
    first_chunk_count = first.chunks_created
    assert first_chunk_count > 0

    file_path.write_text("short second version", encoding="utf-8")
    second = index_library_item(indexing_session, item.item_id)
    assert second is not None

    documents = indexing_session.execute(select(Document)).scalars().all()
    assert len(documents) == 1
    chunks = (
        indexing_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == documents[0].id)
        )
        .scalars()
        .all()
    )
    assert len(chunks) == second.chunks_created
    assert len(chunks) <= first_chunk_count
