import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.learning_event_routes as learning_event_routes_module
import app.api.library_routes as library_routes_module
import app.api.notes_routes as notes_routes_module
import app.api.rag_routes as rag_routes_module
from app.api.learning_event_routes import (
    create_learning_event_endpoint,
    get_learning_event_endpoint,
    get_recent_learning_events_endpoint,
    list_learning_events_endpoint,
)
from app.api.library_routes import (
    generate_library_metadata_draft_endpoint,
    index_library_item_endpoint,
)
from app.api.notes_routes import create_note_endpoint
from app.api.rag_routes import rag_query_library_item_endpoint
from app.embeddings.mock import MockEmbeddingProvider
from app.learning_events.constants import (
    EVENT_BOOK_RAG_QUESTION_ASKED,
    EVENT_LIBRARY_INDEXED,
    EVENT_METADATA_DRAFT_GENERATED,
    EVENT_NOTE_CREATED,
    EVENT_NOTE_EXPORTED,
    SOURCE_LIBRARY,
    SOURCE_NOTES,
)
from app.learning_events.schemas import LearningEventCreate
from app.learning_events.service import create_learning_event, list_learning_events
from app.library.service import create_library_item
from app.models.conversation_turn import ConversationTurn
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
from app.notes.schemas import NoteCreate
from app.rag.schemas import LibraryItemRagQueryRequest


@pytest.fixture
def learning_event_session(monkeypatch):
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
    monkeypatch.setattr(
        learning_event_routes_module, "get_db_session", lambda: session
    )
    try:
        yield session
    finally:
        close_session()
        engine.dispose()


@pytest.fixture
def learning_hook_session(monkeypatch):
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
            ConversationTurn.__table__,
            LearningEvent.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    close_session = session.close
    session.close = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(library_routes_module, "get_db_session", lambda: session)
    monkeypatch.setattr(notes_routes_module, "get_db_session", lambda: session)
    monkeypatch.setattr(rag_routes_module, "get_db_session", lambda: session)
    try:
        yield session
    finally:
        close_session()
        engine.dispose()


def _create_library_item(session: Session, title: str = "Linear Algebra") -> LibraryItem:
    item = LibraryItem(title=title, status="indexed")
    session.add(item)
    session.commit()
    return item


def _create_note(session: Session, title: str = "Vector Spaces") -> Note:
    note = Note(title=title, content_latex="\\section{Vector Spaces}", status="active")
    session.add(note)
    session.commit()
    return note


def _create_indexed_item_with_chunk(
    session: Session,
    title: str = "Linear Algebra",
    content: str = "Vector spaces and linear maps are central.",
) -> LibraryItem:
    item_result = create_library_item(
        session,
        title=title,
        author="Author",
        file_type="txt",
        status="indexed",
    )
    document = Document(
        library_item_id=item_result.item_id,
        title=title,
        file_type="txt",
        file_path=f"/tmp/{title}.txt",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content=content,
            char_start=0,
            char_end=len(content),
            embedding=MockEmbeddingProvider().embed_text(content),
        )
    )
    session.commit()
    item = session.get(LibraryItem, item_result.item_id)
    assert item is not None
    return item


def test_create_learning_event_manually(learning_event_session) -> None:
    library_item = _create_library_item(learning_event_session)

    response = create_learning_event_endpoint(
        LearningEventCreate(
            event_type=EVENT_NOTE_EXPORTED,
            title="Exported note",
            source_type=SOURCE_NOTES,
            library_item_id=str(library_item.id),
            metadata_json={"export_path": "/tmp/note.tex"},
        )
    )

    assert response.id
    assert response.event_type == EVENT_NOTE_EXPORTED
    assert response.title == "Exported note"
    assert response.source_type == SOURCE_NOTES
    assert response.library_item_id == str(library_item.id)
    assert response.metadata_json == {"export_path": "/tmp/note.tex"}


def test_create_event_blank_event_type_fails(learning_event_session) -> None:
    with pytest.raises(ValueError, match="event_type"):
        create_learning_event(learning_event_session, event_type="  ", title="Title")


def test_create_event_blank_title_fails(learning_event_session) -> None:
    with pytest.raises(ValueError, match="title"):
        create_learning_event(
            learning_event_session,
            event_type=EVENT_NOTE_EXPORTED,
            title="   ",
        )


def test_list_events_newest_first(learning_event_session) -> None:
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="First",
        source_type=SOURCE_NOTES,
    )
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_EXPORTED,
        title="Second",
        source_type=SOURCE_NOTES,
    )

    events = list_learning_events(learning_event_session)

    assert [event.title for event in events] == ["Second", "First"]


def test_filter_events_by_event_type(learning_event_session) -> None:
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="Created",
        source_type=SOURCE_NOTES,
    )
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_EXPORTED,
        title="Exported",
        source_type=SOURCE_NOTES,
    )

    response = list_learning_events_endpoint(
        event_type=EVENT_NOTE_CREATED, limit=20, offset=0
    )

    assert response.total == 1
    assert response.events[0].title == "Created"


def test_filter_events_by_source_type(learning_event_session) -> None:
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="Note",
        source_type=SOURCE_NOTES,
    )
    create_learning_event(
        learning_event_session,
        event_type=EVENT_LIBRARY_INDEXED,
        title="Library",
        source_type=SOURCE_LIBRARY,
    )

    response = list_learning_events_endpoint(
        source_type=SOURCE_LIBRARY, limit=20, offset=0
    )

    assert response.total == 1
    assert response.events[0].title == "Library"


def test_filter_events_by_library_item_id(learning_event_session) -> None:
    library_item = _create_library_item(learning_event_session)
    create_learning_event(
        learning_event_session,
        event_type=EVENT_LIBRARY_INDEXED,
        title="Library",
        source_type=SOURCE_LIBRARY,
        library_item_id=library_item.id,
    )
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="Other",
        source_type=SOURCE_NOTES,
    )

    response = list_learning_events_endpoint(
        library_item_id=str(library_item.id), limit=20, offset=0
    )

    assert response.total == 1
    assert response.events[0].library_item_id == str(library_item.id)


def test_filter_events_by_note_id(learning_event_session) -> None:
    note = _create_note(learning_event_session)
    create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="Note",
        source_type=SOURCE_NOTES,
        note_id=note.id,
    )

    response = list_learning_events_endpoint(note_id=str(note.id), limit=20, offset=0)

    assert response.total == 1
    assert response.events[0].note_id == str(note.id)


def test_recent_events_endpoint_returns_limited_newest_events(
    learning_event_session,
) -> None:
    for index in range(3):
        create_learning_event(
            learning_event_session,
            event_type=EVENT_NOTE_CREATED,
            title=f"Event {index}",
            source_type=SOURCE_NOTES,
        )

    response = get_recent_learning_events_endpoint(limit=2)

    assert response.total == 2
    assert [event.title for event in response.events] == ["Event 2", "Event 1"]


def test_get_event_by_id(learning_event_session) -> None:
    event = create_learning_event(
        learning_event_session,
        event_type=EVENT_NOTE_CREATED,
        title="Find Me",
        source_type=SOURCE_NOTES,
    )

    response = get_learning_event_endpoint(event.event_id)

    assert response.id == str(event.event_id)
    assert response.title == "Find Me"


def test_get_nonexistent_event_returns_404(learning_event_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_learning_event_endpoint(uuid.UUID("00000000-0000-0000-0000-000000000000"))

    assert exc_info.value.status_code == 404


def test_invalid_library_item_id_fails_if_provided(learning_event_session) -> None:
    with pytest.raises(ValueError, match="library_item_id"):
        create_learning_event(
            learning_event_session,
            event_type=EVENT_LIBRARY_INDEXED,
            title="Broken",
            library_item_id=uuid.uuid4(),
        )


def test_invalid_note_id_fails_if_provided(learning_event_session) -> None:
    with pytest.raises(ValueError, match="note_id"):
        create_learning_event(
            learning_event_session,
            event_type=EVENT_NOTE_CREATED,
            title="Broken",
            note_id=uuid.uuid4(),
        )


def test_library_indexing_success_creates_learning_event(
    learning_hook_session, tmp_path
) -> None:
    file_path = tmp_path / "book.txt"
    file_path.write_text("A local text book.\n" * 100, encoding="utf-8")
    item = create_library_item(
        learning_hook_session,
        title="Index Me",
        file_path=str(file_path),
        file_type="txt",
    )

    response = index_library_item_endpoint(item.item_id)

    event = learning_hook_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_LIBRARY_INDEXED
    assert event.source_type == SOURCE_LIBRARY
    assert event.library_item_id == item.item_id
    assert event.title == "Indexed library item: Index Me"
    assert event.metadata_json == {
        "chunks_created": response.chunks_created,
        "embeddings_created": response.embeddings_created,
        "document_id": response.document_id,
    }


def test_metadata_draft_generation_creates_learning_event(learning_hook_session) -> None:
    item = _create_indexed_item_with_chunk(learning_hook_session)

    response = generate_library_metadata_draft_endpoint(item.id)

    event = learning_hook_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_METADATA_DRAFT_GENERATED
    assert event.source_type == SOURCE_LIBRARY
    assert event.library_item_id == item.id
    assert event.title == "Generated metadata draft: Linear Algebra"
    assert event.metadata_json == {
        "chunks_used": response.chunks_used,
        "topic_tags_count": len(response.topic_tags),
        "mode": response.mode,
    }


def test_book_scoped_rag_success_creates_learning_event(learning_hook_session) -> None:
    item = _create_indexed_item_with_chunk(learning_hook_session, title="Topology")

    response = rag_query_library_item_endpoint(
        LibraryItemRagQueryRequest(
            library_item_id=str(item.id),
            question="What is topology about?",
            session_id="session-1",
        )
    )

    event = learning_hook_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_BOOK_RAG_QUESTION_ASKED
    assert event.source_type == "rag"
    assert event.library_item_id == item.id
    assert event.session_id == "session-1"
    assert event.title == "Asked question about: Topology"
    assert event.metadata_json == {
        "question": "What is topology about?",
        "total_retrieved": response.total_retrieved,
        "citation_count": len(response.citations),
    }


def test_note_creation_creates_learning_event(learning_hook_session) -> None:
    response = create_note_endpoint(
        NoteCreate(
            title="Vector Spaces",
            content_latex="\\section{Vector Spaces}",
            topic_tags=["linear algebra"],
        )
    )

    event = learning_hook_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_NOTE_CREATED
    assert event.source_type == SOURCE_NOTES
    assert event.note_id == uuid.UUID(response.id)
    assert event.title == "Created note: Vector Spaces"
    assert event.metadata_json == {
        "status": response.status,
        "topic_tags": response.topic_tags,
    }
