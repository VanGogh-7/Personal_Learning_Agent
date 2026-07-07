import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.library_routes as library_routes_module
from app.api.library_routes import index_library_item_endpoint
from app.library.service import create_library_item
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
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
    assert response.chunks_created == 2
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
    chunks = indexing_api_session.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_id == uuid.UUID(response.document_id)
        )
    ).scalars().all()
    assert chunks
    assert all(chunk.embedding is not None for chunk in chunks)
