import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def force_deterministic_providers_for_tests(monkeypatch, request):
    """Keep tests independent from real provider settings in backend/.env."""
    if request.node.get_closest_marker("real_provider") is not None:
        yield
        return
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_CHECKPOINTER_BACKEND", "memory")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()
