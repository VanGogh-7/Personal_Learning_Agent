import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.memory.short_term import (
    ConversationTurnResult,
    build_memory_context,
    create_session_id,
    get_recent_turns,
    save_turn,
)
from app.models.conversation_turn import ConversationTurn


@pytest.fixture
def memory_session():
    """A real SQLAlchemy session backed by an in-memory SQLite database,
    with only the conversation_turns table created. This exercises the
    actual ORM query logic without touching the real PostgreSQL database.
    """
    engine = create_engine("sqlite:///:memory:")
    ConversationTurn.metadata.create_all(engine, tables=[ConversationTurn.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_turn_result(question: str, answer: str) -> ConversationTurnResult:
    return ConversationTurnResult(
        turn_id=uuid.uuid4(),
        session_id="session-a",
        question=question,
        answer=answer,
        created_at=datetime.now(timezone.utc),
    )


def test_create_session_id_returns_non_empty_string() -> None:
    session_id = create_session_id()
    assert isinstance(session_id, str)
    assert session_id.strip() != ""


def test_create_session_id_generates_unique_values() -> None:
    assert create_session_id() != create_session_id()


def test_save_turn_stores_question_and_answer(memory_session) -> None:
    result = save_turn(memory_session, "session-a", "What is X?", "X is Y.")

    assert result.session_id == "session-a"
    assert result.question == "What is X?"
    assert result.answer == "X is Y."
    assert result.turn_id is not None


def test_save_turn_rejects_empty_session_id(memory_session) -> None:
    with pytest.raises(ValueError):
        save_turn(memory_session, "", "question", "answer")


def test_save_turn_rejects_whitespace_only_session_id(memory_session) -> None:
    with pytest.raises(ValueError):
        save_turn(memory_session, "   ", "question", "answer")


def test_save_turn_rejects_empty_question(memory_session) -> None:
    with pytest.raises(ValueError):
        save_turn(memory_session, "session-a", "   ", "answer")


def test_save_turn_rejects_empty_answer(memory_session) -> None:
    with pytest.raises(ValueError):
        save_turn(memory_session, "session-a", "question", "")


def test_get_recent_turns_returns_only_turns_for_requested_session(
    memory_session,
) -> None:
    save_turn(memory_session, "session-a", "Q1", "A1")
    save_turn(memory_session, "session-b", "Q-other", "A-other")
    save_turn(memory_session, "session-a", "Q2", "A2")

    turns = get_recent_turns(memory_session, "session-a", limit=5)

    assert [turn.question for turn in turns] == ["Q1", "Q2"]
    assert all(turn.session_id == "session-a" for turn in turns)


def test_get_recent_turns_respects_limit(memory_session) -> None:
    for i in range(5):
        save_turn(memory_session, "session-a", f"Q{i}", f"A{i}")

    turns = get_recent_turns(memory_session, "session-a", limit=2)

    # Most recent two turns, returned oldest-first.
    assert [turn.question for turn in turns] == ["Q3", "Q4"]


def test_get_recent_turns_returns_empty_list_for_unknown_session(
    memory_session,
) -> None:
    assert get_recent_turns(memory_session, "unknown-session", limit=5) == []


def test_get_recent_turns_rejects_empty_session_id(memory_session) -> None:
    with pytest.raises(ValueError):
        get_recent_turns(memory_session, "", limit=5)


def test_build_memory_context_is_deterministic() -> None:
    turns = [_make_turn_result("Q1", "A1"), _make_turn_result("Q2", "A2")]

    first = build_memory_context(turns)
    second = build_memory_context(turns)

    assert first == second
    assert "Q1" in first and "A1" in first
    assert "Q2" in first and "A2" in first


def test_build_memory_context_handles_empty_turns() -> None:
    assert build_memory_context([]) == ""
