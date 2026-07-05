import uuid

from app.rag.qa import NO_RESULTS_ANSWER, generate_answer
from app.rag.retrieval import RetrievedChunkResult


def _make_chunk(content: str, score: float = 0.1) -> RetrievedChunkResult:
    return RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Intro to Optimization",
        chunk_index=0,
        content=content,
        char_start=0,
        char_end=len(content),
        score=score,
    )


def test_empty_retrieved_chunks_returns_fallback_answer() -> None:
    answer = generate_answer("What is gradient descent?", [])
    assert answer == NO_RESULTS_ANSWER


def test_non_empty_retrieved_chunks_returns_deterministic_grounded_answer() -> None:
    chunk = _make_chunk("Gradient descent is an iterative optimization algorithm.")

    first = generate_answer("What is gradient descent?", [chunk])
    second = generate_answer("What is gradient descent?", [chunk])

    assert first == second
    assert "Gradient descent is an iterative optimization algorithm." in first
    assert "Intro to Optimization" in first


def test_answer_uses_top_ranked_chunk() -> None:
    top_chunk = _make_chunk("The most relevant excerpt.")
    other_chunk = _make_chunk("A less relevant excerpt.")

    answer = generate_answer("question", [top_chunk, other_chunk])

    assert "The most relevant excerpt." in answer
    assert "A less relevant excerpt." not in answer
