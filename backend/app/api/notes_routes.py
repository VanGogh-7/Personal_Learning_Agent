import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.notes.schemas import NoteCreate, NoteListResponse, NoteRead, NoteUpdate
from app.notes.service import (
    DEFAULT_NOTES_LIMIT,
    MAX_NOTES_LIMIT,
    MIN_NOTES_LIMIT,
    NoteResult,
    archive_note,
    create_note,
    get_note,
    list_notes,
    search_notes,
    update_note,
)

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _to_response(note: NoteResult) -> NoteRead:
    return NoteRead(
        id=str(note.note_id),
        title=note.title,
        content_latex=note.content_latex,
        description=note.description,
        library_item_id=str(note.library_item_id) if note.library_item_id else None,
        source_session_id=note.source_session_id,
        topic_tags=note.topic_tags,
        status=note.status,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.post("", response_model=NoteRead)
def create_note_endpoint(request: NoteCreate) -> NoteRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            note = create_note(
                session,
                title=request.title,
                content_latex=request.content_latex,
                description=request.description,
                library_item_id=_parse_optional_uuid(request.library_item_id),
                source_session_id=request.source_session_id,
                topic_tags=request.topic_tags,
                status=request.status,
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

    return _to_response(note)


@router.get("", response_model=NoteListResponse)
def list_notes_endpoint(
    status: str | None = "active",
    library_item_id: str | None = None,
    limit: int = Query(default=DEFAULT_NOTES_LIMIT, ge=MIN_NOTES_LIMIT, le=MAX_NOTES_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> NoteListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            notes = list_notes(
                session,
                status=status,
                library_item_id=_parse_optional_uuid(library_item_id),
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(note) for note in notes]
    return NoteListResponse(notes=responses, total=len(responses))


@router.get("/search", response_model=NoteListResponse)
def search_notes_endpoint(
    keyword: str | None = None,
    status: str | None = "active",
    library_item_id: str | None = None,
    limit: int = Query(default=DEFAULT_NOTES_LIMIT, ge=MIN_NOTES_LIMIT, le=MAX_NOTES_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> NoteListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            notes = search_notes(
                session,
                keyword=keyword,
                status=status,
                library_item_id=_parse_optional_uuid(library_item_id),
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(note) for note in notes]
    return NoteListResponse(notes=responses, total=len(responses))


@router.get("/{note_id}", response_model=NoteRead)
def get_note_endpoint(note_id: uuid.UUID) -> NoteRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            note = get_note(session, note_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return _to_response(note)


@router.patch("/{note_id}", response_model=NoteRead)
def update_note_endpoint(note_id: uuid.UUID, request: NoteUpdate) -> NoteRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            updates = request.model_dump(exclude_unset=True)
            if "library_item_id" in updates:
                updates["library_item_id"] = _parse_optional_uuid(updates["library_item_id"])
            note = update_note(session, note_id, updates)
            if note is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Note not found")
            session.commit()
        except HTTPException:
            raise
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_response(note)


@router.delete("/{note_id}", response_model=NoteRead)
def archive_note_endpoint(note_id: uuid.UUID) -> NoteRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            note = archive_note(session, note_id)
            if note is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Note not found")
            session.commit()
        except HTTPException:
            raise
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_response(note)


def _parse_optional_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("library_item_id must be a valid UUID") from exc
