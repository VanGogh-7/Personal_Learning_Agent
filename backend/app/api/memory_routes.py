from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.memory.long_term import (
    DEFAULT_LIST_LIMIT,
    MAX_IMPORTANCE,
    MAX_LIST_LIMIT,
    MIN_IMPORTANCE,
    MIN_LIST_LIMIT,
    LongTermMemoryResult,
    create_memory,
    list_memories,
    search_memories,
)
from app.memory.schemas import (
    LongTermMemoryCreateRequest,
    LongTermMemoryListResponse,
    LongTermMemoryResponse,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _to_response(memory: LongTermMemoryResult) -> LongTermMemoryResponse:
    return LongTermMemoryResponse(
        id=str(memory.memory_id),
        memory_type=memory.memory_type,
        content=memory.content,
        importance=memory.importance,
        source=memory.source,
        tags=memory.tags,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.post("/long-term", response_model=LongTermMemoryResponse)
def create_long_term_memory_endpoint(
    request: LongTermMemoryCreateRequest,
) -> LongTermMemoryResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            memory = create_memory(
                session,
                memory_type=request.memory_type,
                content=request.content,
                importance=request.importance,
                source=request.source,
                tags=request.tags,
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

    return _to_response(memory)


@router.get("/long-term", response_model=LongTermMemoryListResponse)
def list_long_term_memories_endpoint(
    memory_type: str | None = None,
    min_importance: int | None = Query(default=None, ge=MIN_IMPORTANCE, le=MAX_IMPORTANCE),
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT),
) -> LongTermMemoryListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            memories = list_memories(
                session, memory_type=memory_type, min_importance=min_importance, limit=limit
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(memory) for memory in memories]
    return LongTermMemoryListResponse(memories=responses, total=len(responses))


@router.get("/long-term/search", response_model=LongTermMemoryListResponse)
def search_long_term_memories_endpoint(
    keyword: str = Query(...),
    memory_type: str | None = None,
    min_importance: int | None = Query(default=None, ge=MIN_IMPORTANCE, le=MAX_IMPORTANCE),
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT),
) -> LongTermMemoryListResponse:
    if not keyword.strip():
        raise HTTPException(status_code=422, detail="keyword must not be empty")

    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            memories = search_memories(
                session,
                keyword=keyword,
                memory_type=memory_type,
                min_importance=min_importance,
                limit=limit,
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_response(memory) for memory in memories]
    return LongTermMemoryListResponse(memories=responses, total=len(responses))
