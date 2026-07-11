import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.memory_routes as memory_routes_module
from app.main import app
from app.models.long_term_memory import LongTermMemory

client = TestClient(app)


@pytest.fixture
def memory_session():
    """A real SQLAlchemy session backed by an in-memory SQLite database,
    with only long_term_memories created. Uses StaticPool +
    check_same_thread=False because TestClient runs the (sync) endpoint
    in a worker thread. Never touches the real PostgreSQL database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LongTermMemory.metadata.create_all(engine, tables=[LongTermMemory.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db(monkeypatch, memory_session) -> None:
    monkeypatch.setattr(memory_routes_module, "get_db_session", lambda: memory_session)


def test_create_long_term_memory_works_with_valid_request(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    response = client.post(
        "/api/memory/long-term",
        json={
            "memory_type": "learning_goal",
            "content": "I want to learn algebraic topology after finishing point-set topology.",
            "importance": 4,
            "source": "manual",
            "tags": ["math", "topology"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory_type"] == "learning_goal"
    assert data["importance"] == 4
    assert data["source"] == "manual"
    assert data["tags"] == ["math", "topology"]
    assert data["id"]
    assert data["created_at"]
    assert data["updated_at"]


def test_create_long_term_memory_rejects_invalid_request(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    response = client.post(
        "/api/memory/long-term", json={"memory_type": "", "content": "valid content"}
    )
    assert response.status_code == 422


def test_create_long_term_memory_rejects_invalid_importance(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    response = client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "valid content", "importance": 6},
    )
    assert response.status_code == 422


def test_list_long_term_memories_works_with_type_filter(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "Fact one.", "importance": 2},
    )
    client.post(
        "/api/memory/long-term",
        json={
            "memory_type": "preference",
            "content": "Preference one.",
            "importance": 5,
        },
    )

    response = client.get("/api/memory/long-term", params={"memory_type": "fact"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["memories"][0]["memory_type"] == "fact"


def test_list_long_term_memories_works_with_importance_filter(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "Low importance.", "importance": 2},
    )
    client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "High importance.", "importance": 5},
    )

    response = client.get("/api/memory/long-term", params={"min_importance": 4})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["memories"][0]["content"] == "High importance."


def test_list_long_term_memories_rejects_invalid_limit(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    assert client.get("/api/memory/long-term", params={"limit": 0}).status_code == 422
    assert client.get("/api/memory/long-term", params={"limit": 51}).status_code == 422


def test_list_long_term_memories_rejects_invalid_min_importance(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    assert (
        client.get("/api/memory/long-term", params={"min_importance": 0}).status_code
        == 422
    )
    assert (
        client.get("/api/memory/long-term", params={"min_importance": 6}).status_code
        == 422
    )


def test_search_long_term_memories_works_with_keyword(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "Gradient descent is an algorithm."},
    )
    client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "Cats are great pets."},
    )

    response = client.get(
        "/api/memory/long-term/search", params={"keyword": "gradient"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "Gradient descent" in data["memories"][0]["content"]


def test_search_long_term_memories_requires_keyword(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    response = client.get("/api/memory/long-term/search")
    assert response.status_code == 422


def test_search_long_term_memories_rejects_empty_keyword(
    monkeypatch, memory_session
) -> None:
    _patch_db(monkeypatch, memory_session)

    response = client.get("/api/memory/long-term/search", params={"keyword": "   "})
    assert response.status_code == 422


def test_create_long_term_memory_returns_503_when_database_not_configured(
    monkeypatch,
) -> None:
    def _raise_value_error():
        raise ValueError("DATABASE_URL is required for database operations")

    monkeypatch.setattr(memory_routes_module, "get_db_session", _raise_value_error)

    response = client.post(
        "/api/memory/long-term",
        json={"memory_type": "fact", "content": "valid content"},
    )
    assert response.status_code == 503


def test_existing_endpoints_still_work() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/status").status_code == 200


def test_patch_and_soft_delete_long_term_memory(monkeypatch, memory_session) -> None:
    _patch_db(monkeypatch, memory_session)
    created = client.post(
        "/api/memory/long-term",
        json={
            "memory_type": "semantic",
            "memory_subtype": "user_preference",
            "content": "User prefers concise answers.",
            "structured_data": {"predicate": "answer_style", "object": "concise"},
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    updated = client.patch(
        f"/api/memory/long-term/{memory_id}",
        json={"confidence": 0.8, "importance": 5},
    )
    assert updated.status_code == 200
    assert updated.json()["confidence"] == 0.8

    deleted = client.delete(f"/api/memory/long-term/{memory_id}")
    assert deleted.status_code == 204
    listed = client.get("/api/memory/long-term")
    assert listed.json()["total"] == 0
