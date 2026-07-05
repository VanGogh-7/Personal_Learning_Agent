import uuid

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

import app.api.rag_routes as rag_routes_module
from app.main import app
from app.rag.retrieval import RetrievedChunkResult

client = TestClient(app)


class _FakeSession:
    def close(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _fake_get_db_session():
    return _FakeSession()


def _patch_no_memory(monkeypatch) -> None:
    """Patch memory calls to a no-op/empty state, for tests that only
    care about the retrieval/answer contract, not memory persistence."""
    monkeypatch.setattr(rag_routes_module, "get_db_session", _fake_get_db_session)
    monkeypatch.setattr(
        rag_routes_module, "get_recent_turns", lambda session, session_id, limit: []
    )
    monkeypatch.setattr(
        rag_routes_module,
        "save_turn",
        lambda session, session_id, question, answer, metadata=None: None,
    )


def test_rag_query_returns_answer_and_chunks(monkeypatch) -> None:
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Sample Doc",
        chunk_index=0,
        content="Gradient descent is an optimization algorithm.",
        char_start=0,
        char_end=45,
        score=0.05,
    )

    _patch_no_memory(monkeypatch)
    monkeypatch.setattr(
        rag_routes_module, "retrieve_relevant_chunks", lambda session, question, top_k: [chunk]
    )

    response = client.post(
        "/api/rag/query", json={"question": "What is gradient descent?", "top_k": 3}
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["total_retrieved"] == 1
    assert len(data["retrieved_chunks"]) == 1
    assert isinstance(data["session_id"], str) and data["session_id"]
    assert data["memory"] == {
        "used_recent_turns": 0,
        "saved_current_turn": True,
        "used_long_term_memories": 0,
    }

    returned_chunk = data["retrieved_chunks"][0]
    assert returned_chunk["chunk_id"] == str(chunk.chunk_id)
    assert returned_chunk["document_id"] == str(chunk.document_id)
    assert returned_chunk["document_title"] == "Sample Doc"
    assert returned_chunk["content"] == chunk.content
    assert returned_chunk["char_start"] == 0
    assert returned_chunk["char_end"] == 45
    assert returned_chunk["score"] == 0.05


def test_rag_query_with_no_matches_returns_fallback_answer(monkeypatch) -> None:
    _patch_no_memory(monkeypatch)
    monkeypatch.setattr(
        rag_routes_module, "retrieve_relevant_chunks", lambda session, question, top_k: []
    )

    response = client.post("/api/rag/query", json={"question": "unrelated question"})

    assert response.status_code == 200
    data = response.json()
    assert data["total_retrieved"] == 0
    assert data["retrieved_chunks"] == []
    assert "could not find relevant information" in data["answer"]
    assert data["memory"]["saved_current_turn"] is True


def test_rag_query_works_without_session_id_and_generates_one(monkeypatch) -> None:
    _patch_no_memory(monkeypatch)
    monkeypatch.setattr(
        rag_routes_module, "retrieve_relevant_chunks", lambda session, question, top_k: []
    )

    response = client.post("/api/rag/query", json={"question": "no session id here"})

    assert response.status_code == 200
    assert response.json()["session_id"]


def test_rag_query_works_with_session_id_and_reuses_it(monkeypatch) -> None:
    _patch_no_memory(monkeypatch)
    monkeypatch.setattr(
        rag_routes_module, "retrieve_relevant_chunks", lambda session, question, top_k: []
    )

    response = client.post(
        "/api/rag/query", json={"question": "a question", "session_id": "my-existing-session"}
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "my-existing-session"


def test_rag_query_rejects_empty_question() -> None:
    response = client.post("/api/rag/query", json={"question": "   "})
    assert response.status_code == 422


def test_rag_query_rejects_invalid_top_k() -> None:
    response = client.post("/api/rag/query", json={"question": "valid question", "top_k": 0})
    assert response.status_code == 422

    response = client.post("/api/rag/query", json={"question": "valid question", "top_k": 21})
    assert response.status_code == 422


def test_rag_query_rejects_missing_question() -> None:
    response = client.post("/api/rag/query", json={"top_k": 5})
    assert response.status_code == 422


def test_rag_query_rejects_empty_session_id() -> None:
    response = client.post(
        "/api/rag/query", json={"question": "valid question", "session_id": "   "}
    )
    assert response.status_code == 422


def test_rag_query_returns_503_when_database_not_configured(monkeypatch) -> None:
    def _raise_value_error():
        raise ValueError("DATABASE_URL is required for database operations")

    monkeypatch.setattr(rag_routes_module, "get_db_session", _raise_value_error)

    response = client.post("/api/rag/query", json={"question": "valid question"})
    assert response.status_code == 503


def test_rag_query_returns_503_when_vector_search_fails(monkeypatch) -> None:
    _patch_no_memory(monkeypatch)

    def _raise_db_error(session, question, top_k):
        raise SQLAlchemyError("connection failed")

    monkeypatch.setattr(rag_routes_module, "retrieve_relevant_chunks", _raise_db_error)

    response = client.post("/api/rag/query", json={"question": "valid question"})
    assert response.status_code == 503


def test_existing_endpoints_still_work() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/status").status_code == 200
