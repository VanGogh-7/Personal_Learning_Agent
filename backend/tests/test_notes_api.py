import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.notes_routes as notes_routes_module
from app.models.library_item import LibraryItem
from app.models.learning_event import LearningEvent
from app.models.note import Note
from app.notes.schemas import ChatNoteDraftRequest, NoteCreate, NoteUpdate


@pytest.fixture
def notes_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LibraryItem.metadata.create_all(
        engine,
        tables=[LibraryItem.__table__, Note.__table__, LearningEvent.__table__],
    )
    session = Session(engine, expire_on_commit=False)
    close_session = session.close
    session.close = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(notes_routes_module, "get_db_session", lambda: session)
    try:
        yield session
    finally:
        close_session()
        engine.dispose()


def _create_library_item(notes_session, title: str = "Linear Algebra") -> LibraryItem:
    item = LibraryItem(title=title, status="indexed")
    notes_session.add(item)
    notes_session.commit()
    return item


def _create_note(notes_session, **overrides):
    payload = {
        "title": "Linear Algebra Notes",
        "content_latex": "\\section{Vector Spaces}",
        "description": "Core definitions",
        "topic_tags": ["linear algebra"],
    }
    payload.update(overrides)
    return notes_routes_module.create_note_endpoint(NoteCreate(**payload))


def test_create_note(notes_session) -> None:
    data = _create_note(notes_session)

    assert data.id
    assert data.title == "Linear Algebra Notes"
    assert data.content_latex == "\\section{Vector Spaces}"
    assert data.description == "Core definitions"
    assert data.topic_tags == ["linear algebra"]
    assert data.status == "active"
    assert data.created_at
    assert data.updated_at


def test_create_note_with_library_item(notes_session) -> None:
    library_item = _create_library_item(notes_session)

    data = _create_note(notes_session, library_item_id=str(library_item.id))

    assert data.library_item_id == str(library_item.id)


def test_create_note_invalid_library_item_returns_422(notes_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        notes_routes_module.create_note_endpoint(
            NoteCreate(
                title="Broken",
                content_latex="\\section{Broken}",
                library_item_id="00000000-0000-0000-0000-000000000000",
            )
        )

    assert exc_info.value.status_code == 422
    assert "library_item_id" in exc_info.value.detail


def test_create_note_blank_title_returns_validation_error(notes_session) -> None:
    with pytest.raises(ValidationError):
        NoteCreate(title="   ", content_latex="\\section{Broken}")


def test_list_notes_returns_active_notes(notes_session) -> None:
    _create_note(notes_session, title="Active")
    archived = _create_note(notes_session, title="Archived")
    notes_routes_module.archive_note_endpoint(uuid.UUID(archived.id))

    response = notes_routes_module.list_notes_endpoint(limit=20, offset=0)

    assert response.total == 1
    assert response.notes[0].title == "Active"


def test_get_note_by_id(notes_session) -> None:
    created = _create_note(notes_session, title="Fetch Me")

    response = notes_routes_module.get_note_endpoint(uuid.UUID(created.id))

    assert response.title == "Fetch Me"


def test_get_note_missing_id_returns_404(notes_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        notes_routes_module.get_note_endpoint(
            uuid.UUID("00000000-0000-0000-0000-000000000000")
        )

    assert exc_info.value.status_code == 404


def test_update_note_title_content_and_library_item(notes_session) -> None:
    created = _create_note(notes_session, title="Draft")
    library_item = _create_library_item(notes_session, title="Topology")

    response = notes_routes_module.update_note_endpoint(
        uuid.UUID(created.id),
        NoteUpdate(
            title="Updated",
            content_latex="\\section{Updated}",
            library_item_id=str(library_item.id),
        ),
    )

    assert response.title == "Updated"
    assert response.content_latex == "\\section{Updated}"
    assert response.library_item_id == str(library_item.id)


def test_update_note_invalid_status_returns_422(notes_session) -> None:
    created = _create_note(notes_session)

    with pytest.raises(HTTPException) as exc_info:
        notes_routes_module.update_note_endpoint(
            uuid.UUID(created.id), NoteUpdate(status="deleted")
        )

    assert exc_info.value.status_code == 422
    assert "status" in exc_info.value.detail


def test_delete_archives_note(notes_session) -> None:
    created = _create_note(notes_session, title="Archive Me")

    response = notes_routes_module.archive_note_endpoint(uuid.UUID(created.id))

    assert response.status == "archived"


def test_search_notes_by_keyword(notes_session) -> None:
    _create_note(notes_session, title="Algebra")
    _create_note(notes_session, title="Topology", description="Compactness")

    response = notes_routes_module.search_notes_endpoint(
        keyword="compactness", limit=20, offset=0
    )

    assert response.total == 1
    assert response.notes[0].title == "Topology"


def test_chat_note_draft_endpoint_does_not_save_note(notes_session) -> None:
    response = notes_routes_module.create_chat_note_draft_endpoint(
        ChatNoteDraftRequest(
            question="What is a basis?",
            answer="A basis is a linearly independent spanning set.",
            retrieved_chunks=[],
            session_id="session-1",
        )
    )

    notes = notes_routes_module.list_notes_endpoint(limit=20, offset=0)

    assert response.title == "Notes on What is a basis?"
    assert response.source_session_id == "session-1"
    assert notes.total == 0
