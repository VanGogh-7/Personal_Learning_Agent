import uuid
from datetime import datetime, timezone

from app.memory.long_term import LongTermMemoryResult
from app.memory.short_term import ConversationTurnResult
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


def _make_turn(question: str, answer: str = "some prior answer") -> ConversationTurnResult:
    return ConversationTurnResult(
        turn_id=uuid.uuid4(),
        session_id="session-a",
        question=question,
        answer=answer,
        created_at=datetime.now(timezone.utc),
    )


def _make_long_term_memory(memory_type: str, content: str) -> LongTermMemoryResult:
    return LongTermMemoryResult(
        memory_id=uuid.uuid4(),
        memory_type=memory_type,
        content=content,
        importance=3,
        source="manual",
        tags=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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


def test_answer_includes_most_recent_prior_question_when_turns_present() -> None:
    chunk = _make_chunk("Gradient descent minimizes a loss function.")
    prior_turn = _make_turn("What is a loss function?")

    with_memory = generate_answer("question", [chunk], recent_turns=[prior_turn])
    without_memory = generate_answer("question", [chunk], recent_turns=[])

    assert "recent session context" in with_memory
    assert "What is a loss function?" in with_memory
    assert "recent session context" not in without_memory
    assert without_memory in with_memory


def test_answer_only_mentions_the_single_most_recent_turn() -> None:
    chunk = _make_chunk("Some content.")
    older_turn = _make_turn("An older question")
    latest_turn = _make_turn("The latest question")

    answer = generate_answer("question", [chunk], recent_turns=[older_turn, latest_turn])

    assert "The latest question" in answer
    assert "An older question" not in answer


def test_answer_notes_recent_context_even_with_no_retrieved_chunks() -> None:
    prior_turn = _make_turn("Previous question text")

    answer = generate_answer("question", [], recent_turns=[prior_turn])

    assert answer.startswith(NO_RESULTS_ANSWER)
    assert "recent session context" in answer
    assert "Previous question text" in answer


def test_generate_answer_is_deterministic_with_recent_turns() -> None:
    chunk = _make_chunk("Deterministic content.")
    prior_turn = _make_turn("Same prior question")

    first = generate_answer("question", [chunk], recent_turns=[prior_turn])
    second = generate_answer("question", [chunk], recent_turns=[prior_turn])

    assert first == second


def test_recent_question_is_truncated_defensively() -> None:
    chunk = _make_chunk("Some content.")
    very_long_question = "x" * 500
    prior_turn = _make_turn(very_long_question)

    answer = generate_answer("question", [chunk], recent_turns=[prior_turn])

    assert very_long_question not in answer
    assert "x" * 200 in answer


def test_answer_includes_top_long_term_memory_when_present() -> None:
    chunk = _make_chunk("Some content.")
    memory = _make_long_term_memory("learning_goal", "Learn algebraic topology.")

    with_memory = generate_answer("question", [chunk], long_term_memories=[memory])
    without_memory = generate_answer("question", [chunk], long_term_memories=[])

    assert "long-term memory" in with_memory
    assert "Learn algebraic topology." in with_memory
    assert "learning_goal" in with_memory
    assert "long-term memory" not in without_memory
    assert without_memory in with_memory


def test_answer_only_mentions_the_single_top_long_term_memory() -> None:
    chunk = _make_chunk("Some content.")
    top_memory = _make_long_term_memory("fact", "The most relevant memory.")
    other_memory = _make_long_term_memory("fact", "A less relevant memory.")

    answer = generate_answer(
        "question", [chunk], long_term_memories=[top_memory, other_memory]
    )

    assert "The most relevant memory." in answer
    assert "A less relevant memory." not in answer


def test_long_term_memory_content_is_truncated_defensively() -> None:
    chunk = _make_chunk("Some content.")
    very_long_content = "y" * 500
    memory = _make_long_term_memory("fact", very_long_content)

    answer = generate_answer("question", [chunk], long_term_memories=[memory])

    assert very_long_content not in answer
    assert "y" * 200 in answer


def test_answer_can_include_both_recent_turns_and_long_term_memory() -> None:
    chunk = _make_chunk("Some content.")
    prior_turn = _make_turn("Earlier question")
    memory = _make_long_term_memory("fact", "A relevant fact.")

    answer = generate_answer(
        "question", [chunk], recent_turns=[prior_turn], long_term_memories=[memory]
    )

    assert "recent session context" in answer
    assert "Earlier question" in answer
    assert "long-term memory" in answer
    assert "A relevant fact." in answer
