import json
import socket

import httpx
import pytest

from app.core.config import Settings
from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.mock import MockEmbeddingProvider
from app.embeddings.providers import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    ZhipuEmbeddingProvider,
    get_embedding_provider,
)


def test_embedding_dimension_is_stable_constant() -> None:
    assert EMBEDDING_DIMENSION == 1024


def test_mock_embedding_is_deterministic() -> None:
    provider = MockEmbeddingProvider()
    text = "hello world"

    assert provider.embed_text(text) == provider.embed_text(text)


def test_mock_embedding_has_expected_dimension_and_type() -> None:
    provider = MockEmbeddingProvider()
    vector = provider.embed_text("some chunk of text")

    assert len(vector) == EMBEDDING_DIMENSION
    assert all(isinstance(value, float) for value in vector)


def test_mock_embedding_differs_for_different_text() -> None:
    provider = MockEmbeddingProvider()

    vector_a = provider.embed_text("The quick brown fox jumps over the lazy dog.")
    vector_b = provider.embed_text("Completely unrelated sentence about databases.")

    assert vector_a != vector_b


def test_embed_texts_returns_one_vector_per_input() -> None:
    provider = MockEmbeddingProvider()
    vectors = provider.embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in vectors)
    assert vectors[0] == provider.embed_text("a")


def test_mock_embedding_does_not_open_network_connections(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Mock embedding must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    provider = MockEmbeddingProvider()
    provider.embed_text("no network calls should happen here")


def test_embedding_provider_factory_returns_mock_by_default() -> None:
    provider = get_embedding_provider(Settings(_env_file=None, embedding_provider="mock"))

    assert isinstance(provider, MockEmbeddingProvider)


def test_zhipu_provider_requires_api_key() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="zhipu",
        zhipu_api_key="",
    )

    with pytest.raises(EmbeddingConfigurationError, match="ZHIPU_API_KEY"):
        get_embedding_provider(settings)


def test_zhipu_provider_validates_configured_dimension() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="zhipu",
        zhipu_api_key="test-key",
        zhipu_embedding_dimension=16,
    )

    with pytest.raises(EmbeddingConfigurationError, match="1024"):
        get_embedding_provider(settings)


def test_zhipu_provider_can_use_mocked_http_client_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://open.bigmodel.cn/api/paas/v4/embeddings"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "embedding-3"
        assert payload["input"] == ["alpha", "beta"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1] * EMBEDDING_DIMENSION},
                    {"index": 1, "embedding": [0.2] * EMBEDDING_DIMENSION},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = ZhipuEmbeddingProvider(
        api_key="test-key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="embedding-3",
        dimension=EMBEDDING_DIMENSION,
        client=client,
    )

    embeddings = provider.embed_texts(["alpha", "beta"])

    assert embeddings == [[0.1] * EMBEDDING_DIMENSION, [0.2] * EMBEDDING_DIMENSION]


def test_zhipu_provider_failure_is_clean_and_does_not_leak_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = ZhipuEmbeddingProvider(
        api_key="secret-zhipu-key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="embedding-3",
        dimension=EMBEDDING_DIMENSION,
        client=client,
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed_text("alpha")

    message = str(exc_info.value)
    assert message == "Zhipu embedding provider request failed."
    assert "secret-zhipu-key" not in message
