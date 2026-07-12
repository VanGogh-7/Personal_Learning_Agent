import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.rag_routes as rag_routes_module
from app.api.rag_routes import rag_query_endpoint, rag_query_library_item_endpoint
from app.api.rag_routes import rag_query_library_items_endpoint
from app.embeddings.mock import MockEmbeddingProvider
from app.learning_events.constants import EVENT_MULTI_BOOK_RAG_QUESTION_ASKED
from app.library.service import create_library_item
from app.models.conversation_turn import ConversationTurn
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
from app.rag.retrieval import RetrievedChunkResult
from app.rag.schemas import (
    LibraryItemRagQueryRequest,
    MultiBookRagQueryRequest,
    RagQueryRequest,
)


@pytest.fixture
def scoped_rag_session():
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
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db(monkeypatch, session: Session) -> None:
    monkeypatch.setattr(rag_routes_module, "get_db_session", lambda: session)


def _create_indexed_item(session: Session, title: str, content: str) -> LibraryItem:
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
    session.flush()
    item = session.get(LibraryItem, item_result.item_id)
    assert item is not None
    return item


def test_book_scoped_rag_returns_only_selected_library_item_chunks(
    monkeypatch, scoped_rag_session
) -> None:
    selected = _create_indexed_item(
        scoped_rag_session,
        "Topology",
        "Compact spaces have finite subcovers in topology.",
    )
    other = _create_indexed_item(
        scoped_rag_session,
        "Algebra",
        "Groups, rings, and fields are algebraic structures.",
    )
    selected_id = selected.id
    other_id = other.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_item_endpoint(
        LibraryItemRagQueryRequest(
            library_item_id=str(selected_id),
            question="What does compactness mean?",
            top_k=5,
        )
    )

    assert response.library_item.id == str(selected_id)
    assert response.library_item.title == "Topology"
    assert response.total_retrieved == 1
    assert "Compact spaces" in response.retrieved_chunks[0].content
    assert "algebraic structures" not in response.answer
    assert len(response.citations) == 1
    assert response.citations[0].citation_id == "S1"
    assert response.citations[0].library_item_id == str(selected_id)
    assert response.citations[0].library_title == "Topology"
    assert response.citations[0].library_author == "Author"
    assert response.citations[0].document_title == "Topology"
    assert response.citations[0].document_source_path == "/tmp/Topology.txt"
    assert response.citations[0].chunk_id == response.retrieved_chunks[0].chunk_id
    assert response.citations[0] == response.retrieved_chunks[0].citation

    other_document_ids = {
        str(document.id)
        for document in scoped_rag_session.execute(
            select(Document).where(Document.library_item_id == other_id)
        ).scalars()
    }
    assert response.retrieved_chunks[0].document_id not in other_document_ids


def test_book_scoped_rag_missing_library_item_returns_404(
    monkeypatch, scoped_rag_session
) -> None:
    _patch_db(monkeypatch, scoped_rag_session)

    with pytest.raises(HTTPException) as exc_info:
        rag_query_library_item_endpoint(
            LibraryItemRagQueryRequest(
                library_item_id=str(uuid.uuid4()),
                question="What is this?",
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Library item not found"


def test_book_scoped_rag_unindexed_library_item_returns_400(
    monkeypatch, scoped_rag_session
) -> None:
    unindexed = create_library_item(scoped_rag_session, title="Draft")
    _patch_db(monkeypatch, scoped_rag_session)

    with pytest.raises(HTTPException) as exc_info:
        rag_query_library_item_endpoint(
            LibraryItemRagQueryRequest(
                library_item_id=str(unindexed.item_id),
                question="What is this?",
            )
        )

    assert exc_info.value.status_code == 400
    assert "not been indexed" in exc_info.value.detail


def test_book_scoped_rag_saves_session_metadata(
    monkeypatch, scoped_rag_session
) -> None:
    selected = _create_indexed_item(
        scoped_rag_session,
        "Analysis",
        "Limits and continuity are central to analysis.",
    )
    selected_id = selected.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_item_endpoint(
        LibraryItemRagQueryRequest(
            library_item_id=str(selected_id),
            question="What is analysis about?",
            session_id="session-a",
        )
    )

    turn = scoped_rag_session.execute(select(ConversationTurn)).scalar_one()
    assert response.session_id == "session-a"
    assert turn.metadata_json == {
        "scope": "library_item",
        "library_item_id": str(selected_id),
    }


def test_global_rag_endpoint_still_uses_global_retrieval(monkeypatch) -> None:
    library_item_id = uuid.uuid4()
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Global",
        document_source_path="/tmp/global.md",
        library_item_id=library_item_id,
        library_title="Global Book",
        library_author="Global Author",
        chunk_index=0,
        content="Global retrieval still works.",
        char_start=0,
        char_end=29,
        score=0.01,
    )
    calls = {"global": 0}

    class FakeSession:
        def close(self) -> None:
            pass

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    monkeypatch.setattr(rag_routes_module, "get_db_session", lambda: FakeSession())
    monkeypatch.setattr(
        rag_routes_module, "get_recent_turns", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(rag_routes_module, "save_turn", lambda *args, **kwargs: None)

    def fake_retrieve(session, question, top_k):
        calls["global"] += 1
        return [chunk]

    monkeypatch.setattr(rag_routes_module, "retrieve_relevant_chunks", fake_retrieve)

    response = rag_query_endpoint(RagQueryRequest(question="global question", top_k=3))

    assert calls["global"] == 1
    assert response.total_retrieved == 1
    assert response.retrieved_chunks[0].content == "Global retrieval still works."
    assert response.citations[0].citation_id == "S1"
    assert response.citations[0].chunk_id == response.retrieved_chunks[0].chunk_id
    assert response.citations[0].document_id == response.retrieved_chunks[0].document_id
    assert response.citations[0].library_item_id == str(library_item_id)
    assert response.citations[0].library_title == "Global Book"
    assert response.citations[0].library_author == "Global Author"
    assert response.citations[0].document_title == "Global"
    assert response.citations[0].document_source_path == "/tmp/global.md"
    assert response.citations[0].chunk_index == 0
    assert response.citations[0].score == 0.01
    assert response.citations[0].excerpt == "Global retrieval still works."
    assert response.retrieved_chunks[0].citation == response.citations[0]


def test_multi_book_rag_returns_chunks_only_from_selected_library_items(
    monkeypatch, scoped_rag_session
) -> None:
    selected_a = _create_indexed_item(
        scoped_rag_session,
        "Linear Algebra",
        "Vector spaces have bases and linear maps.",
    )
    selected_b = _create_indexed_item(
        scoped_rag_session,
        "Functional Analysis",
        "Normed spaces and operators extend linear algebra.",
    )
    unselected = _create_indexed_item(
        scoped_rag_session,
        "Botany",
        "Plants convert sunlight into chemical energy.",
    )
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id
    unselected_id = unselected.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_items_endpoint(
        MultiBookRagQueryRequest(
            library_item_ids=[str(selected_a_id), str(selected_b_id)],
            question="What do these materials say about spaces?",
            top_k=5,
            session_id="multi-session",
        )
    )

    returned_library_ids = {
        chunk.citation.library_item_id for chunk in response.retrieved_chunks
    }
    assert returned_library_ids == {str(selected_a_id), str(selected_b_id)}
    assert str(unselected_id) not in returned_library_ids
    assert response.total_retrieved == 2
    assert [item.id for item in response.selected_library_items] == [
        str(selected_a_id),
        str(selected_b_id),
    ]
    assert [item.title for item in response.selected_library_items] == [
        "Linear Algebra",
        "Functional Analysis",
    ]
    assert response.selected_library_items[0].author == "Author"
    assert response.selected_library_items[0].file_type == "txt"
    assert response.selected_library_items[0].status == "indexed"


def test_multi_book_rag_citations_include_library_and_chunk_metadata(
    monkeypatch, scoped_rag_session
) -> None:
    selected_a = _create_indexed_item(
        scoped_rag_session,
        "Topology",
        "Open sets define topological spaces.",
    )
    selected_b = _create_indexed_item(
        scoped_rag_session,
        "Analysis",
        "Limits define continuity in analysis.",
    )
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_items_endpoint(
        MultiBookRagQueryRequest(
            library_item_ids=[str(selected_a_id), str(selected_b_id)],
            question="What is a space?",
            top_k=2,
        )
    )

    assert [citation.citation_id for citation in response.citations] == ["S1", "S2"]
    selected_ids = {str(selected_a_id), str(selected_b_id)}
    for citation, chunk in zip(response.citations, response.retrieved_chunks):
        assert citation == chunk.citation
        assert citation.library_item_id in selected_ids
        assert citation.library_title in {"Topology", "Analysis"}
        assert citation.library_author == "Author"
        assert citation.document_title in {"Topology", "Analysis"}
        assert citation.document_source_path in {
            "/tmp/Topology.txt",
            "/tmp/Analysis.txt",
        }
        assert citation.chunk_id == chunk.chunk_id
        assert citation.document_id == chunk.document_id
        assert citation.chunk_index == chunk.chunk_index
        assert citation.excerpt


def test_multi_book_rag_deduplicates_library_item_ids(
    monkeypatch, scoped_rag_session
) -> None:
    selected_a = _create_indexed_item(
        scoped_rag_session, "Algebra", "Groups have operations."
    )
    selected_b = _create_indexed_item(
        scoped_rag_session, "Geometry", "Triangles have angles."
    )
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_items_endpoint(
        MultiBookRagQueryRequest(
            library_item_ids=[
                str(selected_a_id),
                str(selected_a_id),
                str(selected_b_id),
            ],
            question="What is covered?",
            top_k=5,
        )
    )

    assert [item.id for item in response.selected_library_items] == [
        str(selected_a_id),
        str(selected_b_id),
    ]


def test_multi_book_rag_missing_library_item_returns_404(
    monkeypatch, scoped_rag_session
) -> None:
    selected = _create_indexed_item(scoped_rag_session, "Analysis", "Limits converge.")
    selected_id = selected.id
    _patch_db(monkeypatch, scoped_rag_session)

    with pytest.raises(HTTPException) as exc_info:
        rag_query_library_items_endpoint(
            MultiBookRagQueryRequest(
                library_item_ids=[str(selected_id), str(uuid.uuid4())],
                question="What is this?",
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Library item not found"


def test_multi_book_rag_unindexed_library_item_returns_400(
    monkeypatch, scoped_rag_session
) -> None:
    selected = _create_indexed_item(scoped_rag_session, "Analysis", "Limits converge.")
    unindexed = create_library_item(scoped_rag_session, title="Draft")
    selected_id = selected.id
    unindexed_id = unindexed.item_id
    _patch_db(monkeypatch, scoped_rag_session)

    with pytest.raises(HTTPException) as exc_info:
        rag_query_library_items_endpoint(
            MultiBookRagQueryRequest(
                library_item_ids=[str(selected_id), str(unindexed_id)],
                question="What is this?",
            )
        )

    assert exc_info.value.status_code == 400
    assert "not been indexed" in exc_info.value.detail
    assert "Draft" in exc_info.value.detail


def test_multi_book_rag_saves_memory_metadata_and_learning_event(
    monkeypatch, scoped_rag_session
) -> None:
    selected_a = _create_indexed_item(
        scoped_rag_session, "Algebra", "Groups have operations."
    )
    selected_b = _create_indexed_item(
        scoped_rag_session, "Geometry", "Triangles have angles."
    )
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id
    _patch_db(monkeypatch, scoped_rag_session)

    response = rag_query_library_items_endpoint(
        MultiBookRagQueryRequest(
            library_item_ids=[str(selected_a_id), str(selected_b_id)],
            question="Compare the materials.",
            session_id="session-multi",
        )
    )

    turn = scoped_rag_session.execute(select(ConversationTurn)).scalar_one()
    assert turn.metadata_json == {
        "query_type": "multi_book_rag",
        "scope": "library_items",
        "library_item_ids": [str(selected_a_id), str(selected_b_id)],
        "retrieved_chunk_ids": [chunk.chunk_id for chunk in response.retrieved_chunks],
        "citation_count": len(response.citations),
    }

    event = scoped_rag_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_MULTI_BOOK_RAG_QUESTION_ASKED
    assert event.source_type == "rag"
    assert event.library_item_id is None
    assert event.session_id == "session-multi"
    assert event.title == "Asked question across selected books"
    assert event.metadata_json == {
        "question": "Compare the materials.",
        "library_item_ids": [str(selected_a_id), str(selected_b_id)],
        "library_titles": ["Algebra", "Geometry"],
        "total_retrieved": response.total_retrieved,
        "citation_count": len(response.citations),
    }


def test_failed_multi_book_rag_does_not_create_success_event(
    monkeypatch, scoped_rag_session
) -> None:
    selected = _create_indexed_item(scoped_rag_session, "Analysis", "Limits converge.")
    selected_id = selected.id
    _patch_db(monkeypatch, scoped_rag_session)

    with pytest.raises(HTTPException):
        rag_query_library_items_endpoint(
            MultiBookRagQueryRequest(
                library_item_ids=[str(selected_id), str(uuid.uuid4())],
                question="What is this?",
            )
        )

    events = scoped_rag_session.execute(select(LearningEvent)).scalars().all()
    assert events == []
