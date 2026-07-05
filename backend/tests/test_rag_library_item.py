import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.rag_routes as rag_routes_module
from app.api.rag_routes import rag_query_endpoint, rag_query_library_item_endpoint
from app.embeddings.mock import MockEmbeddingProvider
from app.library.service import create_library_item
from app.models.conversation_turn import ConversationTurn
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from app.rag.retrieval import RetrievedChunkResult
from app.rag.schemas import LibraryItemRagQueryRequest, RagQueryRequest


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
            Document.__table__,
            DocumentChunk.__table__,
            ConversationTurn.__table__,
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


def test_book_scoped_rag_saves_session_metadata(monkeypatch, scoped_rag_session) -> None:
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
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Global",
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
    monkeypatch.setattr(rag_routes_module, "get_recent_turns", lambda *args, **kwargs: [])
    monkeypatch.setattr(rag_routes_module, "save_turn", lambda *args, **kwargs: None)

    def fake_retrieve(session, question, top_k):
        calls["global"] += 1
        return [chunk]

    monkeypatch.setattr(rag_routes_module, "retrieve_relevant_chunks", fake_retrieve)

    response = rag_query_endpoint(RagQueryRequest(question="global question", top_k=3))

    assert calls["global"] == 1
    assert response.total_retrieved == 1
    assert response.retrieved_chunks[0].content == "Global retrieval still works."
