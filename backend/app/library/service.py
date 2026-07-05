import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.library_item import LibraryItem

DEFAULT_LIBRARY_STATUS = "registered"
DEFAULT_LIST_LIMIT = 20
MIN_LIST_LIMIT = 1
MAX_LIST_LIMIT = 100


@dataclass
class LibraryItemResult:
    item_id: uuid.UUID
    title: str
    author: str | None
    description: str | None
    file_path: str | None
    file_type: str | None
    topic_tags: list[str] | None
    status: str
    created_at: datetime
    updated_at: datetime


def _validate_title(title: str) -> None:
    if not title or not title.strip():
        raise ValueError("title must not be empty")


def _validate_status(status: str) -> None:
    if not status or not status.strip():
        raise ValueError("status must not be empty")


def _validate_limit(limit: int) -> None:
    if not (MIN_LIST_LIMIT <= limit <= MAX_LIST_LIMIT):
        raise ValueError(f"limit must be between {MIN_LIST_LIMIT} and {MAX_LIST_LIMIT}")


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    cleaned = [tag.strip() for tag in tags if tag.strip()]
    return cleaned or None


def _to_result(item: LibraryItem) -> LibraryItemResult:
    return LibraryItemResult(
        item_id=item.id,
        title=item.title,
        author=item.author,
        description=item.description,
        file_path=item.file_path,
        file_type=item.file_type,
        topic_tags=item.topic_tags,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def create_library_item(
    session: Session,
    title: str,
    author: str | None = None,
    description: str | None = None,
    file_path: str | None = None,
    file_type: str | None = None,
    topic_tags: list[str] | None = None,
    status: str = DEFAULT_LIBRARY_STATUS,
) -> LibraryItemResult:
    _validate_title(title)
    _validate_status(status)

    item = LibraryItem(
        title=title.strip(),
        author=_clean_optional_text(author),
        description=_clean_optional_text(description),
        file_path=_clean_optional_text(file_path),
        file_type=_clean_optional_text(file_type),
        topic_tags=_clean_tags(topic_tags),
        status=status.strip(),
    )
    session.add(item)
    session.flush()

    return _to_result(item)


def get_library_item(session: Session, item_id: uuid.UUID) -> LibraryItemResult | None:
    item = session.get(LibraryItem, item_id)
    return _to_result(item) if item is not None else None


def list_library_items(
    session: Session,
    status: str | None = None,
    tag: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
) -> list[LibraryItemResult]:
    _validate_limit(limit)
    return _query_library_items(session, keyword=None, status=status, tag=tag, limit=limit)


def search_library_items(
    session: Session,
    keyword: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
) -> list[LibraryItemResult]:
    _validate_limit(limit)
    return _query_library_items(session, keyword=keyword, status=status, tag=tag, limit=limit)


def update_library_item(
    session: Session,
    item_id: uuid.UUID,
    updates: dict,
) -> LibraryItemResult | None:
    item = session.get(LibraryItem, item_id)
    if item is None:
        return None

    if "title" in updates and updates["title"] is not None:
        _validate_title(updates["title"])
        item.title = updates["title"].strip()
    if "author" in updates:
        item.author = _clean_optional_text(updates["author"])
    if "description" in updates:
        item.description = _clean_optional_text(updates["description"])
    if "file_path" in updates:
        item.file_path = _clean_optional_text(updates["file_path"])
    if "file_type" in updates:
        item.file_type = _clean_optional_text(updates["file_type"])
    if "topic_tags" in updates:
        item.topic_tags = _clean_tags(updates["topic_tags"])
    if "status" in updates and updates["status"] is not None:
        _validate_status(updates["status"])
        item.status = updates["status"].strip()

    session.flush()
    return _to_result(item)


def archive_library_item(session: Session, item_id: uuid.UUID) -> LibraryItemResult | None:
    return update_library_item(session, item_id, {"status": "archived"})


def _query_library_items(
    session: Session,
    keyword: str | None,
    status: str | None,
    tag: str | None,
    limit: int,
) -> list[LibraryItemResult]:
    stmt = select(LibraryItem)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                LibraryItem.title.ilike(pattern),
                LibraryItem.author.ilike(pattern),
                LibraryItem.description.ilike(pattern),
            )
        )
    if status and status.strip():
        stmt = stmt.where(LibraryItem.status == status.strip())
    stmt = stmt.order_by(LibraryItem.created_at.desc())

    rows = session.execute(stmt).scalars().all()
    if tag and tag.strip():
        needle = tag.strip()
        rows = [row for row in rows if needle in (row.topic_tags or [])]

    return [_to_result(row) for row in rows[:limit]]
