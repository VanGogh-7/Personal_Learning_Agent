import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.learning_events.schemas import (
    LearningEventCreate,
    LearningEventListResponse,
    LearningEventRead,
)
from app.learning_events.service import (
    DEFAULT_LEARNING_EVENTS_LIMIT,
    MAX_LEARNING_EVENTS_LIMIT,
    MIN_LEARNING_EVENTS_LIMIT,
    LearningEventResult,
    create_learning_event,
    get_learning_event,
    get_recent_learning_events,
    list_learning_events,
)

router = APIRouter(prefix="/api/learning-events", tags=["learning-events"])


def _to_response(event: LearningEventResult) -> LearningEventRead:
    return LearningEventRead(
        id=str(event.event_id),
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        source_type=event.source_type,
        source_id=str(event.source_id) if event.source_id else None,
        library_item_id=str(event.library_item_id) if event.library_item_id else None,
        library_item_title=event.library_item_title,
        note_id=str(event.note_id) if event.note_id else None,
        note_title=event.note_title,
        session_id=event.session_id,
        metadata_json=event.metadata_json,
        created_at=event.created_at,
    )


@router.post("", response_model=LearningEventRead)
def create_learning_event_endpoint(request: LearningEventCreate) -> LearningEventRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            event = create_learning_event(
                session,
                event_type=request.event_type,
                title=request.title,
                description=request.description,
                source_type=request.source_type,
                source_id=_parse_optional_uuid(request.source_id, "source_id"),
                library_item_id=_parse_optional_uuid(
                    request.library_item_id, "library_item_id"
                ),
                note_id=_parse_optional_uuid(request.note_id, "note_id"),
                session_id=request.session_id,
                metadata_json=request.metadata_json,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_response(event)


@router.get("", response_model=LearningEventListResponse)
def list_learning_events_endpoint(
    event_type: str | None = None,
    source_type: str | None = None,
    library_item_id: str | None = None,
    note_id: str | None = None,
    session_id: str | None = None,
    date: date | None = None,
    limit: int = Query(
        default=DEFAULT_LEARNING_EVENTS_LIMIT,
        ge=MIN_LEARNING_EVENTS_LIMIT,
        le=MAX_LEARNING_EVENTS_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> LearningEventListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            events = list_learning_events(
                session,
                event_type=event_type,
                source_type=source_type,
                library_item_id=_parse_optional_uuid(
                    library_item_id, "library_item_id"
                ),
                note_id=_parse_optional_uuid(note_id, "note_id"),
                session_id=session_id,
                event_date=date,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(event) for event in events]
    return LearningEventListResponse(events=responses, total=len(responses))


@router.get("/recent", response_model=LearningEventListResponse)
def get_recent_learning_events_endpoint(
    limit: int = Query(
        default=DEFAULT_LEARNING_EVENTS_LIMIT,
        ge=MIN_LEARNING_EVENTS_LIMIT,
        le=MAX_LEARNING_EVENTS_LIMIT,
    ),
) -> LearningEventListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            events = get_recent_learning_events(session, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(event) for event in events]
    return LearningEventListResponse(events=responses, total=len(responses))


@router.get("/{event_id}", response_model=LearningEventRead)
def get_learning_event_endpoint(event_id: uuid.UUID) -> LearningEventRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            event = get_learning_event(session, event_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    if event is None:
        raise HTTPException(status_code=404, detail="Learning event not found")
    return _to_response(event)


def _parse_optional_uuid(value: str | uuid.UUID | None, field_name: str) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc
