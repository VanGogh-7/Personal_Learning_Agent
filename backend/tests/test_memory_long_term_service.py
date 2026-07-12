import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.memory.long_term import (
    LongTermMemoryResult,
    build_long_term_memory_context,
    create_memory,
    get_memory,
    list_memories,
    search_memories,
)
from app.models.long_term_memory import LongTermMemory


@pytest.fixture
def memory_session():
    """A real SQLAlchemy session backed by an in-memory SQLite database,
    with only the long_term_memories table created. Exercises the actual
    ORM query logic without touching the real PostgreSQL database.
    """
    engine = create_engine("sqlite:///:memory:")
    LongTermMemory.metadata.create_all(engine, tables=[LongTermMemory.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_result(memory_type: str, content: str) -> LongTermMemoryResult:
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


def test_create_memory_validates_memory_type(memory_session) -> None:
    with pytest.raises(ValueError):
        create_memory(memory_session, memory_type="   ", content="valid content")


def test_create_memory_validates_content(memory_session) -> None:
    with pytest.raises(ValueError):
        create_memory(memory_session, memory_type="fact", content="   ")


def test_create_memory_validates_importance(memory_session) -> None:
    with pytest.raises(ValueError):
        create_memory(memory_session, memory_type="fact", content="valid", importance=0)

    with pytest.raises(ValueError):
        create_memory(memory_session, memory_type="fact", content="valid", importance=6)


def test_create_memory_stores_data_correctly(memory_session) -> None:
    result = create_memory(
        memory_session,
        memory_type="learning_goal",
        content="Learn algebraic topology.",
        importance=4,
        source="manual",
        tags=["math", "topology"],
    )

    assert result.memory_id is not None
    assert result.memory_type == "learning_goal"
    assert result.content == "Learn algebraic topology."
    assert result.importance == 4
    assert result.source == "manual"
    assert result.tags == ["math", "topology"]


def test_get_memory_returns_created_memory(memory_session) -> None:
    created = create_memory(memory_session, memory_type="fact", content="Some fact.")

    fetched = get_memory(memory_session, created.memory_id)

    assert fetched is not None
    assert fetched.memory_id == created.memory_id
    assert fetched.content == "Some fact."


def test_get_memory_returns_none_for_unknown_id(memory_session) -> None:
    assert get_memory(memory_session, uuid.uuid4()) is None


def test_list_memories_filters_by_memory_type(memory_session) -> None:
    create_memory(memory_session, memory_type="fact", content="Fact one.")
    create_memory(memory_session, memory_type="preference", content="Preference one.")

    facts = list_memories(memory_session, memory_type="fact")

    assert len(facts) == 1
    assert facts[0].memory_type == "fact"


def test_list_memories_filters_by_min_importance(memory_session) -> None:
    create_memory(
        memory_session, memory_type="fact", content="Low importance.", importance=2
    )
    create_memory(
        memory_session, memory_type="fact", content="High importance.", importance=5
    )

    important = list_memories(memory_session, min_importance=4)

    assert len(important) == 1
    assert important[0].content == "High importance."


def test_list_memories_respects_limit(memory_session) -> None:
    for i in range(5):
        create_memory(memory_session, memory_type="fact", content=f"Fact {i}.")

    results = list_memories(memory_session, limit=2)

    assert len(results) == 2


def test_list_memories_rejects_invalid_limit(memory_session) -> None:
    with pytest.raises(ValueError):
        list_memories(memory_session, limit=0)

    with pytest.raises(ValueError):
        list_memories(memory_session, limit=51)


def test_search_memories_performs_keyword_matching(memory_session) -> None:
    create_memory(
        memory_session, memory_type="fact", content="Gradient descent is an algorithm."
    )
    create_memory(memory_session, memory_type="fact", content="Cats are great pets.")

    results = search_memories(memory_session, keyword="gradient")

    assert len(results) == 1
    assert "Gradient descent" in results[0].content


def test_search_memories_is_case_insensitive(memory_session) -> None:
    create_memory(memory_session, memory_type="fact", content="Gradient Descent Basics")

    results = search_memories(memory_session, keyword="GRADIENT")

    assert len(results) == 1


def test_search_memories_respects_filters(memory_session) -> None:
    create_memory(
        memory_session,
        memory_type="fact",
        content="Gradient descent fact.",
        importance=2,
    )
    create_memory(
        memory_session,
        memory_type="preference",
        content="Gradient descent preference.",
        importance=5,
    )

    results = search_memories(memory_session, keyword="gradient", memory_type="fact")
    assert len(results) == 1
    assert results[0].memory_type == "fact"

    results = search_memories(memory_session, keyword="gradient", min_importance=4)
    assert len(results) == 1
    assert results[0].memory_type == "preference"


def test_search_memories_rejects_empty_keyword(memory_session) -> None:
    with pytest.raises(ValueError):
        search_memories(memory_session, keyword="   ")


def test_build_long_term_memory_context_is_deterministic() -> None:
    memories = [
        _make_result("fact", "Fact A"),
        _make_result("preference", "Preference B"),
    ]

    first = build_long_term_memory_context(memories)
    second = build_long_term_memory_context(memories)

    assert first == second
    assert "Fact A" in first
    assert "Preference B" in first


def test_build_long_term_memory_context_handles_empty_memories() -> None:
    assert build_long_term_memory_context([]) == ""


def test_build_long_term_memory_context_is_bounded() -> None:
    memories = [_make_result("fact", f"Fact {i}") for i in range(10)]

    context = build_long_term_memory_context(memories)

    # Only the first few (DEFAULT_CONTEXT_MEMORY_COUNT) should appear.
    assert "Fact 0" in context
    assert "Fact 1" in context
    assert "Fact 2" in context
    assert "Fact 3" not in context
