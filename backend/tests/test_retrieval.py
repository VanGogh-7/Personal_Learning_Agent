import socket
import uuid

import app.rag.retrieval as retrieval_module
from app.db.vector_search import SimilarChunkResult
from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.mock import MockEmbeddingProvider
from app.rag.retrieval import retrieve_relevant_chunks


class _FakeDocument:
    def __init__(self, title: str) -> None:
        self.title = title


class _FakeSession:
    def __init__(self, documents: dict) -> None:
        self._documents = documents

    def get(self, model, id):
        return self._documents.get(id)


def _make_similar_chunk(document_id, content: str = "some content", distance: float = 0.05):
    return SimilarChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=0,
        content=content,
        char_start=0,
        char_end=len(content),
        distance=distance,
    )


def test_retrieve_relevant_chunks_returns_empty_list_when_no_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module, "search_similar_chunks", lambda session, embedding, limit: []
    )

    result = retrieve_relevant_chunks(_FakeSession({}), "some question", top_k=5)

    assert result == []


def test_retrieve_relevant_chunks_uses_mock_embedding_and_calls_vector_search(monkeypatch) -> None:
    captured = {}

    def fake_search_similar_chunks(session, query_embedding, limit):
        captured["embedding"] = query_embedding
        captured["limit"] = limit
        return []

    monkeypatch.setattr(retrieval_module, "search_similar_chunks", fake_search_similar_chunks)

    retrieve_relevant_chunks(_FakeSession({}), "what is gradient descent?", top_k=7)

    expected_embedding = MockEmbeddingProvider().embed_text("what is gradient descent?")
    assert captured["embedding"] == expected_embedding
    assert len(captured["embedding"]) == EMBEDDING_DIMENSION
    assert captured["limit"] == 7


def test_retrieve_relevant_chunks_returns_typed_results_with_document_title(monkeypatch) -> None:
    document_id = uuid.uuid4()
    chunk = _make_similar_chunk(document_id, content="Gradient descent minimizes a loss function.")

    monkeypatch.setattr(
        retrieval_module, "search_similar_chunks", lambda session, embedding, limit: [chunk]
    )

    session = _FakeSession({document_id: _FakeDocument("Optimization Notes")})
    result = retrieve_relevant_chunks(session, "question", top_k=5)

    assert len(result) == 1
    item = result[0]
    assert item.chunk_id == chunk.chunk_id
    assert item.document_id == document_id
    assert item.document_title == "Optimization Notes"
    assert item.content == "Gradient descent minimizes a loss function."
    assert item.char_start == 0
    assert item.char_end == len(chunk.content)
    assert item.score == chunk.distance


def test_retrieve_relevant_chunks_handles_missing_document_title(monkeypatch) -> None:
    document_id = uuid.uuid4()
    chunk = _make_similar_chunk(document_id)

    monkeypatch.setattr(
        retrieval_module, "search_similar_chunks", lambda session, embedding, limit: [chunk]
    )

    result = retrieve_relevant_chunks(_FakeSession({}), "question", top_k=5)

    assert result[0].document_title is None


def test_retrieve_relevant_chunks_does_not_open_network_connections(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module, "search_similar_chunks", lambda session, embedding, limit: []
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Retrieval must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    retrieve_relevant_chunks(_FakeSession({}), "no network calls should happen here", top_k=5)
