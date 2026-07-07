import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def force_deterministic_providers_for_tests(monkeypatch):
    """Keep tests independent from real provider settings in backend/.env."""
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()

