import pytest
from pydantic import ValidationError

from app.rag.schemas import RagQueryRequest


def test_question_is_required() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest.model_validate({"top_k": 5})


def test_empty_question_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="")


def test_whitespace_only_question_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="   \n\t  ")


def test_top_k_default_is_five() -> None:
    request = RagQueryRequest(question="What is gradient descent?")
    assert request.top_k == 5


def test_top_k_too_low_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="valid question", top_k=0)


def test_top_k_too_high_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="valid question", top_k=21)


def test_top_k_within_range_is_accepted() -> None:
    request = RagQueryRequest(question="valid question", top_k=1)
    assert request.top_k == 1

    request = RagQueryRequest(question="valid question", top_k=20)
    assert request.top_k == 20
