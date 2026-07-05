from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_returns_app_info() -> None:
    response = client.get("/api/status")
    assert response.status_code == 200

    data = response.json()
    assert "app_name" in data
    assert "environment" in data
    assert "version" in data
