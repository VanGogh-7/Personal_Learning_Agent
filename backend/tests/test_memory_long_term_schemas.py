import pytest
from pydantic import ValidationError

from app.memory.schemas import LongTermMemoryCreateRequest


def test_valid_create_request() -> None:
    request = LongTermMemoryCreateRequest(
        memory_type="learning_goal",
        content="I want to learn algebraic topology.",
        importance=4,
        source="manual",
        tags=["math", "topology"],
    )
    assert request.memory_type == "learning_goal"
    assert request.content == "I want to learn algebraic topology."
    assert request.importance == 4
    assert request.source == "manual"
    assert request.tags == ["math", "topology"]


def test_create_request_defaults() -> None:
    request = LongTermMemoryCreateRequest(memory_type="fact", content="Some fact.")
    assert request.importance == 3
    assert request.source == "manual"
    assert request.tags is None


def test_empty_memory_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="", content="valid content")


def test_whitespace_only_memory_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="   ", content="valid content")


def test_empty_content_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="fact", content="")


def test_whitespace_only_content_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="fact", content="   \n\t  ")


def test_importance_too_low_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="fact", content="valid", importance=0)


def test_importance_too_high_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LongTermMemoryCreateRequest(memory_type="fact", content="valid", importance=6)


def test_importance_within_range_is_accepted() -> None:
    low = LongTermMemoryCreateRequest(memory_type="fact", content="valid", importance=1)
    high = LongTermMemoryCreateRequest(
        memory_type="fact", content="valid", importance=5
    )
    assert low.importance == 1
    assert high.importance == 5
