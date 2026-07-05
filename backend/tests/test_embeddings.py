import socket

from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.mock import MockEmbeddingProvider


def test_embedding_dimension_is_stable_constant() -> None:
    assert EMBEDDING_DIMENSION == 16


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
