import socket
import uuid

import app.rag.retrieval as retrieval_module
from app.db.vector_search import SimilarChunkResult
from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.mock import MockEmbeddingProvider
from app.rag.retrieval import retrieve_relevant_chunks


class _FakeDocument:
    def __init__(
        self,
        document_id: uuid.UUID,
        title: str,
        file_path: str | None = None,
        library_item_id: uuid.UUID | None = None,
    ) -> None:
        self.id = document_id
        self.title = title
        self.file_path = file_path
        self.library_item_id = library_item_id


class _FakeLibraryItem:
    def __init__(self, item_id: uuid.UUID, title: str, author: str | None = None) -> None:
        self.id = item_id
        self.title = title
        self.author = author


class _FakeScalarResult:
    def __init__(self, items: list) -> None:
        self._items = items

    def scalars(self):
        return self._items


class _FakeSession:
    def __init__(self, documents: dict, library_items: dict | None = None) -> None:
        self._documents = documents
        self._library_items = library_items or {}

    def get(self, model, id):
        return self._documents.get(id)

    def execute(self, stmt):
        if "library_items" in str(stmt):
            return _FakeScalarResult(list(self._library_items.values()))
        return _FakeScalarResult(list(self._documents.values()))


def _make_similar_chunk(
    document_id,
    content: str = "some content",
    distance: float = 0.05,
    page_start: int | None = None,
    page_end: int | None = None,
    chapter_title: str | None = None,
    section_title: str | None = None,
):
    return SimilarChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=0,
        content=content,
        char_start=0,
        char_end=len(content),
        page_start=page_start,
        page_end=page_end,
        section_type="body",
        chapter_title=chapter_title,
        section_title=section_title,
        distance=distance,
    )


def test_retrieve_relevant_chunks_returns_empty_list_when_no_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module,
        "search_similar_chunks",
        lambda session, embedding, limit, exclude_section_types=(): [],
    )

    result = retrieve_relevant_chunks(_FakeSession({}), "some question", top_k=5)

    assert result == []


def test_retrieve_relevant_chunks_uses_mock_embedding_and_calls_vector_search(monkeypatch) -> None:
    captured = {}

    def fake_search_similar_chunks(
        session, query_embedding, limit, exclude_section_types=()
    ):
        captured["embedding"] = query_embedding
        captured["limit"] = limit
        captured["exclude_section_types"] = exclude_section_types
        return []

    monkeypatch.setattr(retrieval_module, "search_similar_chunks", fake_search_similar_chunks)

    retrieve_relevant_chunks(_FakeSession({}), "what is gradient descent?", top_k=7)

    expected_embedding = MockEmbeddingProvider().embed_text("what is gradient descent?")
    assert captured["embedding"] == expected_embedding
    assert len(captured["embedding"]) == EMBEDDING_DIMENSION
    assert captured["limit"] == 7
    assert "contents" in captured["exclude_section_types"]


def test_retrieve_relevant_chunks_returns_typed_results_with_document_title(monkeypatch) -> None:
    document_id = uuid.uuid4()
    chunk = _make_similar_chunk(
        document_id,
        content="Gradient descent minimizes a loss function.",
        page_start=7,
        page_end=7,
        chapter_title="Chapter 1 Optimization",
        section_title="1.2 Descent Methods",
    )

    monkeypatch.setattr(
        retrieval_module,
        "search_similar_chunks",
        lambda session, embedding, limit, exclude_section_types=(): [chunk],
    )

    library_item_id = uuid.uuid4()
    session = _FakeSession(
        {
            document_id: _FakeDocument(
                document_id,
                "Optimization Notes",
                file_path="/tmp/optimization.md",
                library_item_id=library_item_id,
            )
        },
        {library_item_id: _FakeLibraryItem(library_item_id, "Optimization", "Author")},
    )
    result = retrieve_relevant_chunks(session, "question", top_k=5)

    assert len(result) == 1
    item = result[0]
    assert item.chunk_id == chunk.chunk_id
    assert item.document_id == document_id
    assert item.document_title == "Optimization Notes"
    assert item.document_source_path == "/tmp/optimization.md"
    assert item.library_item_id == library_item_id
    assert item.library_title == "Optimization"
    assert item.library_author == "Author"
    assert item.content == "Gradient descent minimizes a loss function."
    assert item.char_start == 0
    assert item.char_end == len(chunk.content)
    assert item.page_start == 7
    assert item.page_end == 7
    assert item.section_type == "body"
    assert item.chapter_title == "Chapter 1 Optimization"
    assert item.section_title == "1.2 Descent Methods"
    assert item.score == chunk.distance


def test_retrieve_relevant_chunks_handles_missing_document_title(monkeypatch) -> None:
    document_id = uuid.uuid4()
    chunk = _make_similar_chunk(document_id)

    monkeypatch.setattr(
        retrieval_module,
        "search_similar_chunks",
        lambda session, embedding, limit, exclude_section_types=(): [chunk],
    )

    result = retrieve_relevant_chunks(_FakeSession({}), "question", top_k=5)

    assert result[0].document_title is None


def test_retrieve_relevant_chunks_does_not_open_network_connections(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module,
        "search_similar_chunks",
        lambda session, embedding, limit, exclude_section_types=(): [],
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Retrieval must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    retrieve_relevant_chunks(_FakeSession({}), "no network calls should happen here", top_k=5)
