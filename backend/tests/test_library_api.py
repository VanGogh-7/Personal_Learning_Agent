import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.library_routes as library_routes_module
from app.main import app
from app.models.library_item import LibraryItem

client = TestClient(app)


@pytest.fixture
def library_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LibraryItem.metadata.create_all(engine, tables=[LibraryItem.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_db(monkeypatch, library_session) -> None:
    monkeypatch.setattr(library_routes_module, "get_db_session", lambda: library_session)


def _create_item(monkeypatch, library_session, **overrides) -> dict:
    _patch_db(monkeypatch, library_session)
    payload = {
        "title": "Algebra",
        "author": "Emmy Noether",
        "description": "Abstract algebra notes",
        "file_path": "/books/algebra.pdf",
        "file_type": "pdf",
        "topic_tags": ["algebra", "math"],
    }
    payload.update(overrides)
    response = client.post("/api/library/items", json=payload)
    assert response.status_code == 200
    return response.json()


def test_create_library_item(monkeypatch, library_session) -> None:
    data = _create_item(monkeypatch, library_session)

    assert data["title"] == "Algebra"
    assert data["author"] == "Emmy Noether"
    assert data["file_path"] == "/books/algebra.pdf"
    assert data["file_type"] == "pdf"
    assert data["topic_tags"] == ["algebra", "math"]
    assert data["status"] == "registered"
    assert data["id"]
    assert data["created_at"]
    assert data["updated_at"]


def test_create_library_item_rejects_missing_title(monkeypatch, library_session) -> None:
    _patch_db(monkeypatch, library_session)

    response = client.post("/api/library/items", json={"author": "Someone"})

    assert response.status_code == 422


def test_list_library_items(monkeypatch, library_session) -> None:
    _create_item(monkeypatch, library_session, title="Algebra")
    _create_item(monkeypatch, library_session, title="Topology", topic_tags=["topology"])

    response = client.get("/api/library/items")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert {item["title"] for item in data["items"]} == {"Algebra", "Topology"}


def test_get_library_item_by_id(monkeypatch, library_session) -> None:
    created = _create_item(monkeypatch, library_session, title="Analysis")

    response = client.get(f"/api/library/items/{created['id']}")

    assert response.status_code == 200
    assert response.json()["title"] == "Analysis"


def test_get_library_item_missing_id_returns_404(monkeypatch, library_session) -> None:
    _patch_db(monkeypatch, library_session)

    response = client.get("/api/library/items/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_update_library_item(monkeypatch, library_session) -> None:
    created = _create_item(monkeypatch, library_session, title="Draft")

    response = client.patch(
        f"/api/library/items/{created['id']}",
        json={"title": "Updated", "status": "indexed", "topic_tags": ["updated"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["status"] == "indexed"
    assert data["topic_tags"] == ["updated"]


def test_update_library_item_missing_id_returns_404(monkeypatch, library_session) -> None:
    _patch_db(monkeypatch, library_session)

    response = client.patch(
        "/api/library/items/00000000-0000-0000-0000-000000000000",
        json={"title": "Missing"},
    )

    assert response.status_code == 404


def test_search_library_items_by_keyword(monkeypatch, library_session) -> None:
    _create_item(monkeypatch, library_session, title="Algebra", author="Emmy Noether")
    _create_item(monkeypatch, library_session, title="Topology", author="James Munkres")

    response = client.get("/api/library/items/search", params={"keyword": "noether"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Algebra"


def test_filter_library_items_by_tag(monkeypatch, library_session) -> None:
    _create_item(monkeypatch, library_session, title="Algebra", topic_tags=["algebra"])
    _create_item(monkeypatch, library_session, title="Topology", topic_tags=["topology"])

    response = client.get("/api/library/items", params={"tag": "topology"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Topology"


def test_filter_library_items_by_status(monkeypatch, library_session) -> None:
    _create_item(monkeypatch, library_session, title="Registered", status="registered")
    _create_item(monkeypatch, library_session, title="Archived", status="archived")

    response = client.get("/api/library/items", params={"status": "archived"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Archived"


def test_delete_archives_library_item(monkeypatch, library_session) -> None:
    created = _create_item(monkeypatch, library_session, title="Archive Me")

    response = client.delete(f"/api/library/items/{created['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
