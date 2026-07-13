import uuid
from unittest.mock import Mock

import pytest

from app.db.vector_search import (
    MAX_SEARCH_LIMIT,
    build_similarity_query,
    search_similar_chunks,
    search_similar_chunks_for_documents,
    set_chunk_embedding,
)
from app.embeddings.base import EMBEDDING_DIMENSION


def test_build_similarity_query_uses_l2_distance_and_excludes_null_embeddings() -> None:
    stmt = build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=5)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "document_chunks" in compiled
    assert "<->" in compiled
    assert "embedding IS NOT NULL" in compiled
    assert "section_type" in compiled
    assert "contents" in compiled
    assert "index" in compiled
    assert "ORDER BY" in compiled.upper()


def test_build_similarity_query_respects_limit_value() -> None:
    stmt = build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=3)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "LIMIT 3" in compiled.upper()


def test_build_similarity_query_can_include_non_body_sections() -> None:
    stmt = build_similarity_query(
        [0.0] * EMBEDDING_DIMENSION,
        limit=5,
        exclude_section_types=(),
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "NOT IN" not in compiled.upper()
    assert "contents" not in compiled


def test_vector_search_functions_are_importable_and_callable() -> None:
    assert callable(set_chunk_embedding)
    assert callable(search_similar_chunks)


def test_build_similarity_query_rejects_wrong_embedding_dimension() -> None:
    with pytest.raises(ValueError):
        build_similarity_query([0.0] * (EMBEDDING_DIMENSION - 1), limit=5)


def test_build_similarity_query_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError):
        build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=0)

    with pytest.raises(ValueError):
        build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=MAX_SEARCH_LIMIT + 1)


def test_set_chunk_embedding_rejects_wrong_embedding_dimension() -> None:
    # Dimension is validated before the session is used, so no DB access occurs.
    with pytest.raises(ValueError):
        set_chunk_embedding(
            session=None,
            chunk_id=uuid.uuid4(),
            embedding=[0.0] * (EMBEDDING_DIMENSION + 1),
        )


def test_selected_book_routing_keeps_exact_search(monkeypatch) -> None:
    version_id = uuid.uuid4()
    captured: dict[str, bool] = {}
    monkeypatch.setattr(
        "app.db.vector_search._active_embedding_index_version_id",
        lambda: str(version_id),
    )

    def fake_search(*args, force_ann: bool, **kwargs):
        captured["force_ann"] = force_ann
        return []

    monkeypatch.setattr(
        "app.db.vector_search._search_versioned_chunks_for_documents", fake_search
    )
    search_similar_chunks_for_documents(
        Mock(), [0.0] * EMBEDDING_DIMENSION, [uuid.uuid4()], limit=5
    )
    assert captured["force_ann"] is False


def test_large_scope_routing_uses_ann(monkeypatch) -> None:
    version_id = uuid.uuid4()
    captured: dict[str, bool] = {}
    monkeypatch.setattr(
        "app.db.vector_search._active_embedding_index_version_id",
        lambda: str(version_id),
    )

    def fake_search(*args, force_ann: bool, **kwargs):
        captured["force_ann"] = force_ann
        return []

    monkeypatch.setattr(
        "app.db.vector_search._search_versioned_chunks_for_documents", fake_search
    )
    search_similar_chunks_for_documents(
        Mock(),
        [0.0] * EMBEDDING_DIMENSION,
        [uuid.uuid4() for _ in range(6)],
        limit=5,
    )
    assert captured["force_ann"] is True
