import uuid

import pytest

from app.db.vector_search import (
    MAX_SEARCH_LIMIT,
    build_similarity_query,
    search_similar_chunks,
    set_chunk_embedding,
)
from app.embeddings.base import EMBEDDING_DIMENSION


def test_build_similarity_query_uses_l2_distance_and_excludes_null_embeddings() -> None:
    stmt = build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=5)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "document_chunks" in compiled
    assert "<->" in compiled
    assert "embedding IS NOT NULL" in compiled
    assert "ORDER BY" in compiled.upper()


def test_build_similarity_query_respects_limit_value() -> None:
    stmt = build_similarity_query([0.0] * EMBEDDING_DIMENSION, limit=3)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "LIMIT 3" in compiled.upper()


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
