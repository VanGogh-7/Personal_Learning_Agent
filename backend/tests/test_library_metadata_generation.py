import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.library_routes as library_routes_module
from app.api.library_routes import (
    generate_library_metadata_draft_endpoint,
    update_library_item_endpoint,
)
from app.library.metadata_generation import (
    LibraryMetadataGenerationError,
    generate_library_metadata_draft,
)
from app.library.schemas import LibraryItemUpdate
from app.library.service import create_library_item
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem


@pytest.fixture
def metadata_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LibraryItem.metadata.create_all(
        engine,
        tables=[LibraryItem.__table__, Document.__table__, DocumentChunk.__table__],
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db(monkeypatch, metadata_session) -> None:
    monkeypatch.setattr(library_routes_module, "get_db_session", lambda: metadata_session)


def _create_indexed_item(metadata_session, *, with_chunks: bool = True):
    item = create_library_item(
        metadata_session,
        title="Linear Algebra",
        author="Test Author",
        description="Original description",
        file_path="/books/linear-algebra.txt",
        file_type="txt",
        topic_tags=["original"],
        status="indexed",
    )
    document = Document(
        library_item_id=item.item_id,
        title="Linear Algebra",
        file_path="/books/linear-algebra.txt",
        file_type="txt",
    )
    metadata_session.add(document)
    metadata_session.flush()

    if with_chunks:
        for index, content in enumerate(
            [
                "Vector spaces and linear combinations define spans. "
                "Bases describe coordinates.",
                "Linear maps preserve vector addition. Eigenvalues appear in transformations.",
                "Matrices represent linear maps and basis changes.",
            ]
        ):
            metadata_session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    char_start=index * 100,
                    char_end=index * 100 + len(content),
                )
            )
        metadata_session.flush()

    metadata_session.commit()
    return item


def test_indexed_library_item_can_generate_metadata_draft(metadata_session) -> None:
    item = _create_indexed_item(metadata_session)

    draft = generate_library_metadata_draft(metadata_session, item.item_id)

    assert draft is not None
    assert draft.library_item_id == item.item_id
    assert draft.title == "Linear Algebra"
    assert draft.chunks_used == 3
    assert draft.mode == "deterministic"
    assert draft.summary
    assert "Linear Algebra" in draft.summary
    assert draft.topic_tags


def test_metadata_draft_is_deterministic(metadata_session) -> None:
    item = _create_indexed_item(metadata_session)

    first = generate_library_metadata_draft(metadata_session, item.item_id)
    second = generate_library_metadata_draft(metadata_session, item.item_id)

    assert first is not None
    assert second is not None
    assert first.summary == second.summary
    assert first.topic_tags == second.topic_tags
    assert first.topic_tags[:4] == ["linear", "vector", "maps", "algebra"]


def test_metadata_draft_does_not_mutate_library_item(metadata_session) -> None:
    item = _create_indexed_item(metadata_session)

    draft = generate_library_metadata_draft(metadata_session, item.item_id)

    assert draft is not None
    refreshed = metadata_session.get(LibraryItem, item.item_id)
    assert refreshed is not None
    assert refreshed.description == "Original description"
    assert refreshed.topic_tags == ["original"]


def test_metadata_draft_missing_library_item_returns_none(metadata_session) -> None:
    assert generate_library_metadata_draft(metadata_session, uuid.uuid4()) is None


def test_metadata_draft_requires_indexed_library_item(metadata_session) -> None:
    item = create_library_item(metadata_session, title="Unindexed")

    with pytest.raises(LibraryMetadataGenerationError, match="Index this item"):
        generate_library_metadata_draft(metadata_session, item.item_id)


def test_metadata_draft_requires_chunks(metadata_session) -> None:
    item = _create_indexed_item(metadata_session, with_chunks=False)

    with pytest.raises(LibraryMetadataGenerationError, match="no chunks"):
        generate_library_metadata_draft(metadata_session, item.item_id)


def test_metadata_draft_endpoint_returns_draft(monkeypatch, metadata_session) -> None:
    _patch_db(monkeypatch, metadata_session)
    item = _create_indexed_item(metadata_session)

    response = generate_library_metadata_draft_endpoint(item.item_id)

    assert response.library_item_id == str(item.item_id)
    assert response.title == "Linear Algebra"
    assert response.summary
    assert response.topic_tags[:4] == ["linear", "vector", "maps", "algebra"]
    assert response.chunks_used == 3
    assert response.mode == "deterministic"

    refreshed = metadata_session.get(LibraryItem, item.item_id)
    assert refreshed is not None
    assert refreshed.description == "Original description"
    assert refreshed.topic_tags == ["original"]


def test_metadata_draft_endpoint_missing_id_returns_404(
    monkeypatch, metadata_session
) -> None:
    _patch_db(monkeypatch, metadata_session)

    with pytest.raises(HTTPException) as exc_info:
        generate_library_metadata_draft_endpoint(
            uuid.UUID("00000000-0000-0000-0000-000000000000")
        )

    assert exc_info.value.status_code == 404


def test_metadata_draft_endpoint_unindexed_item_returns_409(
    monkeypatch, metadata_session
) -> None:
    _patch_db(monkeypatch, metadata_session)
    item = create_library_item(metadata_session, title="Unindexed")

    with pytest.raises(HTTPException) as exc_info:
        generate_library_metadata_draft_endpoint(item.item_id)

    assert exc_info.value.status_code == 409
    assert "Index this item" in exc_info.value.detail


def test_metadata_draft_endpoint_indexed_item_with_no_chunks_returns_409(
    monkeypatch, metadata_session
) -> None:
    _patch_db(monkeypatch, metadata_session)
    item = _create_indexed_item(metadata_session, with_chunks=False)

    with pytest.raises(HTTPException) as exc_info:
        generate_library_metadata_draft_endpoint(item.item_id)

    assert exc_info.value.status_code == 409
    assert "no chunks" in exc_info.value.detail


def test_saving_generated_metadata_uses_existing_patch_endpoint(
    monkeypatch, metadata_session
) -> None:
    _patch_db(monkeypatch, metadata_session)
    item = _create_indexed_item(metadata_session)
    draft = generate_library_metadata_draft_endpoint(item.item_id)

    saved = update_library_item_endpoint(
        item.item_id,
        LibraryItemUpdate(
            description=draft.summary,
            topic_tags=draft.topic_tags,
        ),
    )

    assert saved.description == draft.summary
    assert saved.topic_tags == draft.topic_tags

    stored = metadata_session.execute(
        select(LibraryItem).where(LibraryItem.id == item.item_id)
    ).scalar_one()
    assert stored.description == draft.summary
    assert stored.topic_tags == draft.topic_tags
