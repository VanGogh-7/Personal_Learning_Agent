import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.library_item import LibraryItem
from app.models.note import Note

DEFAULT_NOTE_STATUS = "active"
ARCHIVED_NOTE_STATUS = "archived"
SUPPORTED_NOTE_STATUSES = {DEFAULT_NOTE_STATUS, ARCHIVED_NOTE_STATUS}
DEFAULT_NOTES_LIMIT = 20
MIN_NOTES_LIMIT = 1
MAX_NOTES_LIMIT = 100


@dataclass
class NoteResult:
    note_id: uuid.UUID
    title: str
    content_latex: str
    description: str | None
    library_item_id: uuid.UUID | None
    source_session_id: str | None
    topic_tags: list[str] | None
    status: str
    created_at: datetime
    updated_at: datetime


def create_note(
    session: Session,
    title: str,
    content_latex: str,
    description: str | None = None,
    library_item_id: uuid.UUID | None = None,
    source_session_id: str | None = None,
    topic_tags: list[str] | None = None,
    status: str = DEFAULT_NOTE_STATUS,
) -> NoteResult:
    _validate_title(title)
    _validate_content_latex(content_latex)
    _validate_status(status)
    _validate_library_item(session, library_item_id)

    note = Note(
        title=title.strip(),
        content_latex=content_latex,
        description=_clean_optional_text(description),
        library_item_id=library_item_id,
        source_session_id=_clean_optional_text(source_session_id),
        topic_tags=_clean_tags(topic_tags),
        status=status.strip(),
    )
    session.add(note)
    session.flush()
    return _to_result(note)


def get_note(session: Session, note_id: uuid.UUID) -> NoteResult | None:
    note = session.get(Note, note_id)
    return _to_result(note) if note is not None else None


def list_notes(
    session: Session,
    status: str | None = DEFAULT_NOTE_STATUS,
    library_item_id: uuid.UUID | None = None,
    limit: int = DEFAULT_NOTES_LIMIT,
    offset: int = 0,
) -> list[NoteResult]:
    _validate_limit(limit)
    _validate_offset(offset)
    if status is not None:
        _validate_status(status)

    stmt = select(Note)
    if status is not None:
        stmt = stmt.where(Note.status == status.strip())
    if library_item_id is not None:
        stmt = stmt.where(Note.library_item_id == library_item_id)
    stmt = stmt.order_by(Note.created_at.desc()).offset(offset).limit(limit)
    return [_to_result(row) for row in session.execute(stmt).scalars().all()]


def search_notes(
    session: Session,
    keyword: str | None,
    status: str | None = DEFAULT_NOTE_STATUS,
    library_item_id: uuid.UUID | None = None,
    limit: int = DEFAULT_NOTES_LIMIT,
    offset: int = 0,
) -> list[NoteResult]:
    _validate_limit(limit)
    _validate_offset(offset)
    if status is not None:
        _validate_status(status)

    stmt = select(Note)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(Note.title.ilike(pattern), Note.description.ilike(pattern))
        )
    if status is not None:
        stmt = stmt.where(Note.status == status.strip())
    if library_item_id is not None:
        stmt = stmt.where(Note.library_item_id == library_item_id)
    stmt = stmt.order_by(Note.created_at.desc()).offset(offset).limit(limit)
    return [_to_result(row) for row in session.execute(stmt).scalars().all()]


def update_note(
    session: Session, note_id: uuid.UUID, updates: dict
) -> NoteResult | None:
    note = session.get(Note, note_id)
    if note is None:
        return None

    if "title" in updates and updates["title"] is not None:
        _validate_title(updates["title"])
        note.title = updates["title"].strip()
    if "content_latex" in updates and updates["content_latex"] is not None:
        _validate_content_latex(updates["content_latex"])
        note.content_latex = updates["content_latex"]
    if "description" in updates:
        note.description = _clean_optional_text(updates["description"])
    if "library_item_id" in updates:
        note.library_item_id = _parse_library_item_update(updates["library_item_id"])
        _validate_library_item(session, note.library_item_id)
    if "source_session_id" in updates:
        note.source_session_id = _clean_optional_text(updates["source_session_id"])
    if "topic_tags" in updates:
        note.topic_tags = _clean_tags(updates["topic_tags"])
    if "status" in updates and updates["status"] is not None:
        _validate_status(updates["status"])
        note.status = updates["status"].strip()

    session.flush()
    return _to_result(note)


def archive_note(session: Session, note_id: uuid.UUID) -> NoteResult | None:
    return update_note(session, note_id, {"status": ARCHIVED_NOTE_STATUS})


def _to_result(note: Note) -> NoteResult:
    return NoteResult(
        note_id=note.id,
        title=note.title,
        content_latex=note.content_latex,
        description=note.description,
        library_item_id=note.library_item_id,
        source_session_id=note.source_session_id,
        topic_tags=note.topic_tags,
        status=note.status,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _validate_title(title: str) -> None:
    if not title or not title.strip():
        raise ValueError("title must not be empty")


def _validate_content_latex(content_latex: str | None) -> None:
    if content_latex is None:
        raise ValueError("content_latex is required")


def _validate_status(status: str) -> None:
    if not status or not status.strip():
        raise ValueError("status must not be empty")
    if status.strip() not in SUPPORTED_NOTE_STATUSES:
        raise ValueError("status must be active or archived")


def _validate_library_item(session: Session, library_item_id: uuid.UUID | None) -> None:
    if (
        library_item_id is not None
        and session.get(LibraryItem, library_item_id) is None
    ):
        raise ValueError("library_item_id does not reference an existing library item")


def _validate_limit(limit: int) -> None:
    if not (MIN_NOTES_LIMIT <= limit <= MAX_NOTES_LIMIT):
        raise ValueError(
            f"limit must be between {MIN_NOTES_LIMIT} and {MAX_NOTES_LIMIT}"
        )


def _validate_offset(offset: int) -> None:
    if offset < 0:
        raise ValueError("offset must be non-negative")


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


def _parse_library_item_update(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
