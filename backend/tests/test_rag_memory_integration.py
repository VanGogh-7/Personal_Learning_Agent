import pytest
import socket
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.rag_routes as rag_routes_module
from app.main import app
from app.memory.short_term import get_recent_turns
from app.models.conversation_turn import ConversationTurn

client = TestClient(app)


@pytest.fixture
def memory_session():
    """A real SQLAlchemy session backed by an in-memory SQLite database,
    with only conversation_turns created. Retrieval (which needs pgvector)
    is monkeypatched separately in each test, so this never touches the
    real PostgreSQL database.

    Uses StaticPool + check_same_thread=False because TestClient runs the
    (sync) endpoint in a worker thread, and plain in-memory SQLite
    connections are otherwise thread-affined.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ConversationTurn.metadata.create_all(engine, tables=[ConversationTurn.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db_and_retrieval(monkeypatch, memory_session, retrieved=None):
    monkeypatch.setattr(rag_routes_module, "get_db_session", lambda: memory_session)
    monkeypatch.setattr(
        rag_routes_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: retrieved or [],
    )


def test_request_without_session_id_generates_one(monkeypatch, memory_session) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)

    response = client.post("/api/rag/query", json={"question": "first question"})

    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert session_id

    # The turn was actually persisted under the generated session_id.
    turns = get_recent_turns(memory_session, session_id, limit=5)
    assert len(turns) == 1
    assert turns[0].question == "first question"


def test_request_with_session_id_reuses_it(monkeypatch, memory_session) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)

    response = client.post(
        "/api/rag/query", json={"question": "a question", "session_id": "fixed-session"}
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "fixed-session"


def test_recent_turns_are_loaded_and_reflected_in_memory_metadata(
    monkeypatch, memory_session
) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    session_id = "session-with-history"

    first = client.post(
        "/api/rag/query", json={"question": "first question", "session_id": session_id}
    )
    assert first.json()["memory"]["used_recent_turns"] == 0

    second = client.post(
        "/api/rag/query", json={"question": "second question", "session_id": session_id}
    )
    assert second.json()["memory"]["used_recent_turns"] == 1
    # The QA layer deterministically mentions the most recent prior
    # question (bounded to that single turn), not just a generic note.
    assert "recent session context" in second.json()["answer"]
    assert "first question" in second.json()["answer"]


def test_current_turn_is_saved_after_answer_generation(monkeypatch, memory_session) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    session_id = "session-save-check"

    response = client.post(
        "/api/rag/query", json={"question": "please remember this", "session_id": session_id}
    )
    answer = response.json()["answer"]

    turns = get_recent_turns(memory_session, session_id, limit=5)
    assert len(turns) == 1
    assert turns[0].question == "please remember this"
    assert turns[0].answer == answer


def test_empty_retrieval_still_saves_current_turn_with_fallback_answer(
    monkeypatch, memory_session
) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session, retrieved=[])
    session_id = "session-empty-retrieval"

    response = client.post(
        "/api/rag/query", json={"question": "nothing matches this", "session_id": session_id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_retrieved"] == 0
    assert "could not find relevant information" in data["answer"]
    assert data["memory"]["saved_current_turn"] is True

    turns = get_recent_turns(memory_session, session_id, limit=5)
    assert len(turns) == 1
    assert turns[0].answer == data["answer"]


def test_rag_query_with_memory_does_not_open_network_connections(
    monkeypatch, memory_session
) -> None:
    # Calls the endpoint function directly (not via TestClient/HTTP):
    # TestClient's own AnyIO transport opens local socketpairs internally,
    # which would make a socket.socket patch a false positive here.
    _patch_db_and_retrieval(monkeypatch, memory_session)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("RAG + memory flow must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    from app.rag.schemas import RagQueryRequest

    result = rag_routes_module.rag_query_endpoint(
        RagQueryRequest(question="no network calls please")
    )
    assert result.answer
