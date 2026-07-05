import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.library.schemas import LibraryItemCreate, LibraryItemListResponse, LibraryItemRead, LibraryItemUpdate
from app.library.service import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    MIN_LIST_LIMIT,
    LibraryItemResult,
    archive_library_item,
    create_library_item,
    get_library_item,
    list_library_items,
    search_library_items,
    update_library_item,
)

router = APIRouter(prefix="/api/library", tags=["library"])


def _to_response(item: LibraryItemResult) -> LibraryItemRead:
    return LibraryItemRead(
        id=str(item.item_id),
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


@router.post("/items", response_model=LibraryItemRead)
def create_library_item_endpoint(request: LibraryItemCreate) -> LibraryItemRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            item = create_library_item(
                session,
                title=request.title,
                author=request.author,
                description=request.description,
                file_path=request.file_path,
                file_type=request.file_type,
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

    return _to_response(item)


@router.get("/items", response_model=LibraryItemListResponse)
def list_library_items_endpoint(
    status: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT),
) -> LibraryItemListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            items = list_library_items(session, status=status, tag=tag, limit=limit)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(item) for item in items]
    return LibraryItemListResponse(items=responses, total=len(responses))


@router.get("/items/search", response_model=LibraryItemListResponse)
def search_library_items_endpoint(
    keyword: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT),
) -> LibraryItemListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            items = search_library_items(
                session, keyword=keyword, status=status, tag=tag, limit=limit
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(item) for item in items]
    return LibraryItemListResponse(items=responses, total=len(responses))


@router.get("/items/{item_id}", response_model=LibraryItemRead)
def get_library_item_endpoint(item_id: uuid.UUID) -> LibraryItemRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            item = get_library_item(session, item_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    return _to_response(item)


@router.patch("/items/{item_id}", response_model=LibraryItemRead)
def update_library_item_endpoint(
    item_id: uuid.UUID, request: LibraryItemUpdate
) -> LibraryItemRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            item = update_library_item(
                session,
                item_id,
                request.model_dump(exclude_unset=True),
            )
            if item is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Library item not found")
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

    return _to_response(item)


@router.delete("/items/{item_id}", response_model=LibraryItemRead)
def archive_library_item_endpoint(item_id: uuid.UUID) -> LibraryItemRead:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            item = archive_library_item(session, item_id)
            if item is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Library item not found")
            session.commit()
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_response(item)
