import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.library_item import LibraryItem
from app.models.note import Note
from app.notes.service import (
    archive_note,
    create_note,
    get_note,
    list_notes,
    search_notes,
    update_note,
)


@pytest.fixture
def notes_session():
    engine = create_engine("sqlite:///:memory:")
    LibraryItem.metadata.create_all(
        engine, tables=[LibraryItem.__table__, Note.__table__]
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _create_library_item(session: Session, title: str = "Algebra") -> LibraryItem:
    item = LibraryItem(title=title, status="indexed")
    session.add(item)
    session.flush()
    return item


def test_create_note_successfully(notes_session) -> None:
    note = create_note(
        notes_session,
        title="Linear Algebra Notes",
        content_latex="\\section{Vector Spaces}",
        description="Core definitions",
        topic_tags=["linear algebra", "vector spaces"],
    )

    assert note.note_id is not None
    assert note.title == "Linear Algebra Notes"
    assert note.content_latex == "\\section{Vector Spaces}"
    assert note.description == "Core definitions"
    assert note.topic_tags == ["linear algebra", "vector spaces"]
    assert note.status == "active"


def test_create_note_with_library_item(notes_session) -> None:
    library_item = _create_library_item(notes_session)

    note = create_note(
        notes_session,
        title="Book Notes",
        content_latex="\\section{Notes}",
        library_item_id=library_item.id,
    )

    assert note.library_item_id == library_item.id


def test_create_note_invalid_library_item_fails(notes_session) -> None:
    with pytest.raises(ValueError, match="library_item_id"):
        create_note(
            notes_session,
            title="Broken Association",
            content_latex="\\section{Notes}",
            library_item_id=uuid.uuid4(),
        )


def test_create_note_blank_title_fails(notes_session) -> None:
    with pytest.raises(ValueError, match="title"):
        create_note(notes_session, title="   ", content_latex="\\section{Notes}")


def test_list_notes_returns_active_notes_by_default(notes_session) -> None:
    create_note(notes_session, title="Active", content_latex="\\section{A}")
    archived = create_note(
        notes_session, title="Archived", content_latex="\\section{B}"
    )
    archive_note(notes_session, archived.note_id)

    results = list_notes(notes_session)

    assert len(results) == 1
    assert results[0].title == "Active"


def test_get_note_by_id(notes_session) -> None:
    created = create_note(
        notes_session, title="Fetch Me", content_latex="\\section{Fetch}"
    )

    fetched = get_note(notes_session, created.note_id)

    assert fetched is not None
    assert fetched.note_id == created.note_id
    assert fetched.title == "Fetch Me"


def test_update_note_title_and_content(notes_session) -> None:
    created = create_note(
        notes_session, title="Draft", content_latex="\\section{Draft}"
    )

    updated = update_note(
        notes_session,
        created.note_id,
        {"title": "Updated", "content_latex": "\\section{Updated}"},
    )

    assert updated is not None
    assert updated.title == "Updated"
    assert updated.content_latex == "\\section{Updated}"


def test_update_note_library_item(notes_session) -> None:
    created = create_note(
        notes_session, title="Draft", content_latex="\\section{Draft}"
    )
    library_item = _create_library_item(notes_session, title="Topology")

    updated = update_note(
        notes_session,
        created.note_id,
        {"library_item_id": library_item.id},
    )

    assert updated is not None
    assert updated.library_item_id == library_item.id


def test_update_note_invalid_status_fails(notes_session) -> None:
    created = create_note(
        notes_session, title="Draft", content_latex="\\section{Draft}"
    )

    with pytest.raises(ValueError, match="status"):
        update_note(notes_session, created.note_id, {"status": "deleted"})


def test_archive_note_sets_status_archived(notes_session) -> None:
    created = create_note(
        notes_session, title="Archive Me", content_latex="\\section{Archive}"
    )

    archived = archive_note(notes_session, created.note_id)

    assert archived is not None
    assert archived.status == "archived"


def test_search_notes_matches_title_and_description(notes_session) -> None:
    create_note(notes_session, title="Algebra", content_latex="\\section{A}")
    create_note(
        notes_session,
        title="Topology",
        content_latex="\\section{T}",
        description="Compactness and connectedness",
    )

    by_title = search_notes(notes_session, keyword="algebra")
    by_description = search_notes(notes_session, keyword="compactness")

    assert len(by_title) == 1
    assert by_title[0].title == "Algebra"
    assert len(by_description) == 1
    assert by_description[0].title == "Topology"
