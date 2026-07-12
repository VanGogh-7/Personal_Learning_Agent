import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.library_routes as library_routes_module
from app.api.library_routes import import_pdfs_endpoint, index_library_item_endpoint
from app.core.config import get_settings
from app.library.schemas import LibraryPdfImportRequest
from app.library.service import create_library_item
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
from app.models.pdf_processing import DocumentPage, PdfProcessingVersion
from tests.pdf_fixtures import make_pdf_bytes


@pytest.fixture
def indexing_api_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LibraryItem.metadata.create_all(
        engine,
        tables=[
            LibraryItem.__table__,
            Note.__table__,
            Document.__table__,
            PdfProcessingVersion.__table__,
            DocumentPage.__table__,
            DocumentChunk.__table__,
            LearningEvent.__table__,
        ],
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def clear_settings_cache_after_test():
    try:
        yield
    finally:
        get_settings.cache_clear()


def _patch_db(monkeypatch, indexing_api_session) -> None:
    monkeypatch.setattr(
        library_routes_module, "get_db_session", lambda: indexing_api_session
    )


def test_index_library_item_endpoint_success(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    file_path = tmp_path / "book.txt"
    file_path.write_text("A local text book.\n" * 100, encoding="utf-8")
    item = create_library_item(
        indexing_api_session,
        title="Index Me",
        file_path=str(file_path),
        file_type="txt",
    )

    response = index_library_item_endpoint(item.item_id)

    assert response.item_id == str(item.item_id)
    assert response.document_id
    assert response.status == "indexed"
    assert response.chunks_created > 0
    assert response.embeddings_created == response.chunks_created

    document = indexing_api_session.get(Document, uuid.UUID(response.document_id))
    assert document is not None
    assert document.library_item_id == item.item_id


def test_index_library_item_endpoint_missing_id_returns_404(
    monkeypatch, indexing_api_session
) -> None:
    _patch_db(monkeypatch, indexing_api_session)

    with pytest.raises(HTTPException) as exc_info:
        index_library_item_endpoint(uuid.UUID("00000000-0000-0000-0000-000000000000"))

    assert exc_info.value.status_code == 404


def test_index_library_item_endpoint_indexes_pdf(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    file_path = tmp_path / "book.pdf"
    file_path.write_bytes(make_pdf_bytes(["PDF page one.", "PDF page two."]))
    item = create_library_item(
        indexing_api_session,
        title="Index Me",
        file_path=str(file_path),
        file_type="pdf",
    )

    response = index_library_item_endpoint(item.item_id)

    assert response.status == "indexed"
    assert response.chunks_created == 1
    refreshed = indexing_api_session.get(LibraryItem, item.item_id)
    assert refreshed is not None
    assert refreshed.status == "indexed"


def test_index_library_item_endpoint_creates_chunks_with_embeddings(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    file_path = tmp_path / "book.md"
    file_path.write_text("# Notes\n\nCompactness matters.\n" * 80, encoding="utf-8")
    item = create_library_item(
        indexing_api_session,
        title="Index Me",
        file_path=str(file_path),
        file_type="md",
    )

    response = index_library_item_endpoint(item.item_id)

    assert response.document_id
    chunks = (
        indexing_api_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == uuid.UUID(response.document_id)
            )
        )
        .scalars()
        .all()
    )
    assert chunks
    assert all(chunk.embedding is not None for chunk in chunks)


def test_import_pdfs_endpoint_copies_to_managed_storage_and_indexes(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    storage_dir = tmp_path / "managed-library"
    monkeypatch.setenv("LIBRARY_STORAGE_DIR", str(storage_dir))
    get_settings.cache_clear()
    source_path = tmp_path / "Analysis.pdf"
    source_path.write_bytes(
        make_pdf_bytes(["Complete metric spaces.", "Banach spaces."])
    )

    response = import_pdfs_endpoint(
        LibraryPdfImportRequest(source_paths=[str(source_path)])
    )

    assert response.total == 1
    imported = response.items[0]
    assert imported.original_filename == "Analysis.pdf"
    assert imported.file_size_bytes == source_path.stat().st_size
    assert imported.library_item.title == "Analysis"
    assert imported.library_item.status == "indexed"
    assert imported.library_item.file_type == "pdf"
    stored_item = indexing_api_session.get(
        LibraryItem, uuid.UUID(imported.library_item.id)
    )
    assert stored_item is not None and stored_item.file_path is not None
    managed_path = Path(stored_item.file_path)
    assert managed_path != source_path
    assert managed_path.parent == storage_dir
    assert "Analysis.pdf" in managed_path.name
    assert managed_path.exists()
    assert imported.index_result.status == "indexed"
    assert imported.index_result.chunks_created > 0

    source_path.unlink()
    reindex_response = index_library_item_endpoint(uuid.UUID(imported.library_item.id))
    assert reindex_response.status == "indexed"


def test_import_pdfs_endpoint_rejects_non_pdf_source(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    storage_dir = tmp_path / "managed-library"
    monkeypatch.setenv("LIBRARY_STORAGE_DIR", str(storage_dir))
    get_settings.cache_clear()
    source_path = tmp_path / "notes.txt"
    source_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        import_pdfs_endpoint(LibraryPdfImportRequest(source_paths=[str(source_path)]))

    assert exc_info.value.status_code == 400
    assert "Only .pdf files can be imported" in str(exc_info.value.detail)

    fake_pdf_path = tmp_path / "fake.pdf"
    fake_pdf_path.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(HTTPException) as invalid_pdf_exc:
        import_pdfs_endpoint(LibraryPdfImportRequest(source_paths=[str(fake_pdf_path)]))

    assert invalid_pdf_exc.value.status_code == 400
    assert "Selected file is not a valid PDF" in str(invalid_pdf_exc.value.detail)

    malformed_pdf_path = tmp_path / "malformed.pdf"
    malformed_pdf_path.write_bytes(b"%PDF-broken")
    with pytest.raises(HTTPException):
        import_pdfs_endpoint(
            LibraryPdfImportRequest(source_paths=[str(malformed_pdf_path)])
        )

    assert not list(storage_dir.glob("*.pdf"))


def test_import_pdfs_endpoint_duplicate_imports_create_separate_managed_copies(
    monkeypatch, indexing_api_session, tmp_path
) -> None:
    _patch_db(monkeypatch, indexing_api_session)
    monkeypatch.setenv("LIBRARY_STORAGE_DIR", str(tmp_path / "managed-library"))
    get_settings.cache_clear()
    source_path = tmp_path / "Analysis.pdf"
    source_path.write_bytes(make_pdf_bytes(["Duplicate import."]))

    response = import_pdfs_endpoint(
        LibraryPdfImportRequest(source_paths=[str(source_path), str(source_path)])
    )

    assert response.total == 2
    item_ids = {item.library_item.id for item in response.items}
    stored_items = [
        indexing_api_session.get(LibraryItem, uuid.UUID(item_id))
        for item_id in item_ids
    ]
    managed_paths = {
        item.file_path for item in stored_items if item is not None and item.file_path
    }
    assert len(item_ids) == 2
    assert len(managed_paths) == 2
    assert all(Path(path).exists() for path in managed_paths)
