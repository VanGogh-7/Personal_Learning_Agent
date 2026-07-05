import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.rag_routes as rag_routes_module
from app.main import app
from app.memory.long_term import create_memory
from app.models.conversation_turn import ConversationTurn
from app.models.long_term_memory import LongTermMemory

client = TestClient(app)


@pytest.fixture
def memory_session():
    """A real SQLAlchemy session backed by an in-memory SQLite database,
    with conversation_turns and long_term_memories created. Retrieval
    (which needs pgvector) is monkeypatched separately, so this never
    touches the real PostgreSQL database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [ConversationTurn.__table__, LongTermMemory.__table__]
    ConversationTurn.metadata.create_all(engine, tables=tables)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db_and_retrieval(monkeypatch, memory_session) -> None:
    monkeypatch.setattr(rag_routes_module, "get_db_session", lambda: memory_session)
    monkeypatch.setattr(
        rag_routes_module, "retrieve_relevant_chunks", lambda session, question, top_k: []
    )


def test_include_long_term_memory_defaults_to_false(monkeypatch, memory_session) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    create_memory(memory_session, memory_type="fact", content="gradient descent details")
    memory_session.commit()

    response = client.post(
        "/api/rag/query", json={"question": "tell me about gradient descent"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory"]["used_long_term_memories"] == 0
    assert "long-term memory" not in data["answer"]


def test_existing_behavior_unchanged_when_flag_false(monkeypatch, memory_session) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    create_memory(memory_session, memory_type="fact", content="gradient descent details")
    memory_session.commit()

    response = client.post(
        "/api/rag/query",
        json={"question": "tell me about gradient descent", "include_long_term_memory": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory"]["used_long_term_memories"] == 0
    assert "long-term memory" not in data["answer"]


def test_long_term_memory_used_when_flag_true_and_keyword_matches(
    monkeypatch, memory_session
) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    create_memory(
        memory_session,
        memory_type="fact",
        content="Gradient descent is an iterative optimization algorithm.",
    )
    memory_session.commit()

    response = client.post(
        "/api/rag/query",
        json={"question": "gradient descent", "include_long_term_memory": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory"]["used_long_term_memories"] == 1
    assert "long-term memory" in data["answer"]
    assert "Gradient descent is an iterative optimization algorithm." in data["answer"]


def test_long_term_memory_not_used_when_flag_true_but_no_keyword_match(
    monkeypatch, memory_session
) -> None:
    _patch_db_and_retrieval(monkeypatch, memory_session)
    create_memory(memory_session, memory_type="fact", content="Cats are great pets.")
    memory_session.commit()

    response = client.post(
        "/api/rag/query",
        json={"question": "gradient descent", "include_long_term_memory": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory"]["used_long_term_memories"] == 0
    assert "long-term memory" not in data["answer"]
