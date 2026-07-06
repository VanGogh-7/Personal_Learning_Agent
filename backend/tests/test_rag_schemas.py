import pytest
from pydantic import ValidationError

from app.rag.schemas import MultiBookRagQueryRequest, RagQueryRequest


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


def test_request_without_session_id_is_valid() -> None:
    request = RagQueryRequest(question="valid question")
    assert request.session_id is None


def test_request_with_valid_session_id_is_valid() -> None:
    request = RagQueryRequest(question="valid question", session_id="my-session")
    assert request.session_id == "my-session"


def test_session_id_is_stripped() -> None:
    request = RagQueryRequest(question="valid question", session_id="  my-session  ")
    assert request.session_id == "my-session"


def test_empty_session_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="valid question", session_id="")


def test_whitespace_only_session_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RagQueryRequest(question="valid question", session_id="   ")


def test_multi_book_request_deduplicates_library_item_ids() -> None:
    request = MultiBookRagQueryRequest(
        question="valid question",
        library_item_ids=[" item-a ", "item-a", "item-b"],
    )

    assert request.library_item_ids == ["item-a", "item-b"]


def test_multi_book_request_rejects_empty_library_item_ids() -> None:
    with pytest.raises(ValidationError):
        MultiBookRagQueryRequest(question="valid question", library_item_ids=[])
