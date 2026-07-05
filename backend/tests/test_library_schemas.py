import pytest
from pydantic import ValidationError

from app.library.schemas import LibraryItemCreate, LibraryItemUpdate


def test_create_library_item_requires_title() -> None:
    with pytest.raises(ValidationError):
        LibraryItemCreate(title="")

    with pytest.raises(ValidationError):
        LibraryItemCreate(title="   ")


def test_create_library_item_defaults_status() -> None:
    item = LibraryItemCreate(title="Algebra")

    assert item.title == "Algebra"
    assert item.status == "registered"


def test_create_library_item_normalizes_optional_metadata() -> None:
    item = LibraryItemCreate(
        title="  Topology  ",
        author="  Munkres  ",
        description="  Point-set topology  ",
        file_path="  /books/topology.pdf  ",
        file_type="  pdf  ",
        topic_tags=[" topology ", "", "math"],
    )

    assert item.title == "Topology"
    assert item.author == "Munkres"
    assert item.description == "Point-set topology"
    assert item.file_path == "/books/topology.pdf"
    assert item.file_type == "pdf"
    assert item.topic_tags == ["topology", "math"]


def test_update_library_item_rejects_blank_title_or_status() -> None:
    with pytest.raises(ValidationError):
        LibraryItemUpdate(title="   ")

    with pytest.raises(ValidationError):
        LibraryItemUpdate(status="   ")
