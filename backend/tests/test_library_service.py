import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.library.service import (
    archive_library_item,
    create_library_item,
    get_library_item,
    list_library_items,
    search_library_items,
    update_library_item,
)
from app.models.library_item import LibraryItem


@pytest.fixture
def library_session():
    engine = create_engine("sqlite:///:memory:")
    LibraryItem.metadata.create_all(engine, tables=[LibraryItem.__table__])
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_library_item_stores_metadata(library_session) -> None:
    item = create_library_item(
        library_session,
        title="Linear Algebra Done Right",
        author="Sheldon Axler",
        description="Finite-dimensional vector spaces.",
        file_path="/library/linear-algebra.pdf",
        file_type="pdf",
        topic_tags=["linear algebra", "math"],
    )

    assert item.item_id is not None
    assert item.title == "Linear Algebra Done Right"
    assert item.author == "Sheldon Axler"
    assert item.file_path == "/library/linear-algebra.pdf"
    assert item.file_type == "pdf"
    assert item.topic_tags == ["linear algebra", "math"]
    assert item.status == "registered"


def test_create_library_item_rejects_blank_title(library_session) -> None:
    with pytest.raises(ValueError):
        create_library_item(library_session, title="   ")


def test_get_library_item_returns_created_item(library_session) -> None:
    created = create_library_item(library_session, title="Topology")

    fetched = get_library_item(library_session, created.item_id)

    assert fetched is not None
    assert fetched.item_id == created.item_id
    assert fetched.title == "Topology"


def test_get_library_item_returns_none_for_unknown_id(library_session) -> None:
    assert get_library_item(library_session, uuid.uuid4()) is None


def test_list_library_items_filters_by_status_and_tag(library_session) -> None:
    create_library_item(library_session, title="Active Algebra", topic_tags=["algebra"])
    create_library_item(
        library_session,
        title="Archived Topology",
        topic_tags=["topology"],
        status="archived",
    )

    active = list_library_items(library_session, status="registered")
    topology = list_library_items(library_session, tag="topology")

    assert len(active) == 1
    assert active[0].title == "Active Algebra"
    assert len(topology) == 1
    assert topology[0].title == "Archived Topology"


def test_search_library_items_matches_title_author_and_description(
    library_session,
) -> None:
    create_library_item(library_session, title="Algebra", author="Emmy Noether")
    create_library_item(
        library_session, title="Analysis", description="Measure theory notes"
    )
    create_library_item(library_session, title="Combinatorics")

    author_matches = search_library_items(library_session, keyword="noether")
    description_matches = search_library_items(library_session, keyword="measure")

    assert len(author_matches) == 1
    assert author_matches[0].title == "Algebra"
    assert len(description_matches) == 1
    assert description_matches[0].title == "Analysis"


def test_search_library_items_filters_by_status_and_tag(library_session) -> None:
    create_library_item(
        library_session,
        title="Algebra Notes",
        topic_tags=["algebra"],
        status="registered",
    )
    create_library_item(
        library_session,
        title="Algebra Archive",
        topic_tags=["algebra"],
        status="archived",
    )
    create_library_item(
        library_session,
        title="Topology Notes",
        topic_tags=["topology"],
        status="registered",
    )

    results = search_library_items(
        library_session, keyword="algebra", tag="algebra", status="registered"
    )

    assert len(results) == 1
    assert results[0].title == "Algebra Notes"


def test_update_library_item_updates_metadata(library_session) -> None:
    created = create_library_item(library_session, title="Draft")

    updated = update_library_item(
        library_session,
        created.item_id,
        {
            "title": "Updated Title",
            "author": "Updated Author",
            "topic_tags": ["math", "updated"],
            "status": "indexed",
        },
    )

    assert updated is not None
    assert updated.title == "Updated Title"
    assert updated.author == "Updated Author"
    assert updated.topic_tags == ["math", "updated"]
    assert updated.status == "indexed"


def test_update_library_item_returns_none_for_unknown_id(library_session) -> None:
    assert (
        update_library_item(library_session, uuid.uuid4(), {"title": "Missing"}) is None
    )


def test_archive_library_item_sets_status_archived(library_session) -> None:
    created = create_library_item(library_session, title="To Archive")

    archived = archive_library_item(library_session, created.item_id)

    assert archived is not None
    assert archived.status == "archived"
