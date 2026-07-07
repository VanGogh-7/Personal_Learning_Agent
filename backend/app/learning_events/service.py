import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning_events.constants import LEARNING_EVENT_TYPES
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note

DEFAULT_LEARNING_EVENTS_LIMIT = 20
MIN_LEARNING_EVENTS_LIMIT = 1
MAX_LEARNING_EVENTS_LIMIT = 100


@dataclass
class LearningEventResult:
    event_id: uuid.UUID
    event_type: str
    title: str
    description: str | None
    source_type: str | None
    source_id: uuid.UUID | None
    library_item_id: uuid.UUID | None
    library_item_title: str | None
    note_id: uuid.UUID | None
    note_title: str | None
    session_id: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


def create_learning_event(
    session: Session,
    event_type: str,
    title: str,
    description: str | None = None,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    library_item_id: uuid.UUID | None = None,
    note_id: uuid.UUID | None = None,
    session_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> LearningEventResult:
    normalized_event_type = _normalize_event_type(event_type)
    normalized_title = _normalize_required_text(title, "title")
    _validate_library_item(session, library_item_id)
    _validate_note(session, note_id)

    event = LearningEvent(
        event_type=normalized_event_type,
        title=normalized_title,
        description=_clean_optional_text(description),
        source_type=_clean_optional_text(source_type),
        source_id=source_id,
        library_item_id=library_item_id,
        note_id=note_id,
        session_id=_clean_optional_text(session_id),
        metadata_json=metadata_json,
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    return _to_result(
        event,
        library_item_title=_related_library_item_title(session, event.library_item_id),
        note_title=_related_note_title(session, event.note_id),
    )


def get_learning_event(
    session: Session,
    event_id: uuid.UUID,
) -> LearningEventResult | None:
    event = session.get(LearningEvent, event_id)
    if event is None:
        return None
    return _to_result(
        event,
        library_item_title=_related_library_item_title(session, event.library_item_id),
        note_title=_related_note_title(session, event.note_id),
    )


def list_learning_events(
    session: Session,
    event_type: str | None = None,
    source_type: str | None = None,
    library_item_id: uuid.UUID | None = None,
    note_id: uuid.UUID | None = None,
    session_id: str | None = None,
    event_date: date | None = None,
    limit: int = DEFAULT_LEARNING_EVENTS_LIMIT,
    offset: int = 0,
) -> list[LearningEventResult]:
    _validate_limit(limit)
    _validate_offset(offset)

    stmt = select(LearningEvent)
    if event_type and event_type.strip():
        stmt = stmt.where(LearningEvent.event_type == event_type.strip())
    if source_type and source_type.strip():
        stmt = stmt.where(LearningEvent.source_type == source_type.strip())
    if library_item_id is not None:
        stmt = stmt.where(LearningEvent.library_item_id == library_item_id)
    if note_id is not None:
        stmt = stmt.where(LearningEvent.note_id == note_id)
    if session_id and session_id.strip():
        stmt = stmt.where(LearningEvent.session_id == session_id.strip())
    if event_date is not None:
        start = datetime.combine(event_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(event_date, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(LearningEvent.created_at >= start).where(
            LearningEvent.created_at <= end
        )

    stmt = stmt.order_by(LearningEvent.created_at.desc()).offset(offset).limit(limit)
    events = session.execute(stmt).scalars().all()
    library_titles = _library_item_titles(session, [event.library_item_id for event in events])
    note_titles = _note_titles(session, [event.note_id for event in events])
    return [
        _to_result(
            event,
            library_item_title=library_titles.get(event.library_item_id),
            note_title=note_titles.get(event.note_id),
        )
        for event in events
    ]


def get_recent_learning_events(
    session: Session,
    limit: int = DEFAULT_LEARNING_EVENTS_LIMIT,
) -> list[LearningEventResult]:
    return list_learning_events(session, limit=limit, offset=0)


def _to_result(
    event: LearningEvent,
    *,
    library_item_title: str | None = None,
    note_title: str | None = None,
) -> LearningEventResult:
    return LearningEventResult(
        event_id=event.id,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        source_type=event.source_type,
        source_id=event.source_id,
        library_item_id=event.library_item_id,
        library_item_title=library_item_title,
        note_id=event.note_id,
        note_title=note_title,
        session_id=event.session_id,
        metadata_json=event.metadata_json,
        created_at=event.created_at,
    )


def _library_item_titles(
    session: Session, item_ids: list[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    ids = [item_id for item_id in set(item_ids) if item_id is not None]
    if not ids:
        return {}
    return {
        item.id: item.title
        for item in session.execute(
            select(LibraryItem).where(LibraryItem.id.in_(ids))
        ).scalars()
    }


def _note_titles(session: Session, note_ids: list[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = [note_id for note_id in set(note_ids) if note_id is not None]
    if not ids:
        return {}
    return {
        note.id: note.title
        for note in session.execute(select(Note).where(Note.id.in_(ids))).scalars()
    }


def _related_library_item_title(
    session: Session, library_item_id: uuid.UUID | None
) -> str | None:
    if library_item_id is None:
        return None
    item = session.get(LibraryItem, library_item_id)
    return item.title if item is not None else None


def _related_note_title(session: Session, note_id: uuid.UUID | None) -> str | None:
    if note_id is None:
        return None
    note = session.get(Note, note_id)
    return note.title if note is not None else None


def _normalize_event_type(event_type: str) -> str:
    normalized = _normalize_required_text(event_type, "event_type")
    if normalized not in LEARNING_EVENT_TYPES:
        raise ValueError("event_type is not supported")
    return normalized


def _normalize_required_text(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_library_item(
    session: Session,
    library_item_id: uuid.UUID | None,
) -> None:
    if library_item_id is not None and session.get(LibraryItem, library_item_id) is None:
        raise ValueError("library_item_id does not reference an existing library item")


def _validate_note(session: Session, note_id: uuid.UUID | None) -> None:
    if note_id is not None and session.get(Note, note_id) is None:
        raise ValueError("note_id does not reference an existing note")


def _validate_limit(limit: int) -> None:
    if not (MIN_LEARNING_EVENTS_LIMIT <= limit <= MAX_LEARNING_EVENTS_LIMIT):
        raise ValueError(
            f"limit must be between {MIN_LEARNING_EVENTS_LIMIT} and "
            f"{MAX_LEARNING_EVENTS_LIMIT}"
        )


def _validate_offset(offset: int) -> None:
    if offset < 0:
        raise ValueError("offset must be non-negative")
