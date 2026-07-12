from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.core.config import get_settings
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
    LongTermMemoryUpdateRequest,
)
from app.memory.models import MemoryStatus
from app.memory.repository import get_memory_record, soft_delete_memory
from app.embeddings.providers import get_embedding_provider
import uuid

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
        namespace=memory.namespace,
        subject_id=memory.subject_id,
        memory_subtype=memory.memory_subtype,
        structured_data=memory.structured_data,
        confidence=memory.confidence,
        status=memory.status,
        source_type=memory.source_type,
        supersedes_id=str(memory.supersedes_id) if memory.supersedes_id else None,
        valid_from=memory.valid_from,
        valid_until=memory.valid_until,
        last_accessed_at=memory.last_accessed_at,
        access_count=memory.access_count,
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
                namespace=request.namespace,
                subject_id=request.subject_id,
                memory_subtype=request.memory_subtype.value
                if request.memory_subtype
                else None,
                structured_data=request.structured_data,
                confidence=request.confidence,
                source_type=request.source,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(
                status_code=503, detail="Database is unavailable"
            ) from exc
    finally:
        session.close()

    return _to_response(memory)


@router.get("/long-term", response_model=LongTermMemoryListResponse)
def list_long_term_memories_endpoint(
    memory_type: str | None = None,
    min_importance: int | None = Query(
        default=None, ge=MIN_IMPORTANCE, le=MAX_IMPORTANCE
    ),
    limit: int = Query(
        default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT
    ),
    memory_subtype: str | None = None,
    status: MemoryStatus | None = MemoryStatus.ACTIVE,
    namespace: str | None = None,
    offset: int = Query(default=0, ge=0),
) -> LongTermMemoryListResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            memories = list_memories(
                session,
                memory_type=memory_type,
                min_importance=min_importance,
                limit=limit,
                memory_subtype=memory_subtype,
                status=status.value if status else None,
                namespace=namespace,
                offset=offset,
            )
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=503, detail="Database is unavailable"
            ) from exc
    finally:
        session.close()

    responses = [_to_response(memory) for memory in memories]
    return LongTermMemoryListResponse(memories=responses, total=len(responses))


@router.patch("/long-term/{memory_id}", response_model=LongTermMemoryResponse)
def update_long_term_memory_endpoint(
    memory_id: uuid.UUID, request: LongTermMemoryUpdateRequest
) -> LongTermMemoryResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        memory = get_memory_record(session, memory_id, include_deleted=True)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        changes = request.model_dump(exclude_unset=True)
        if "content" in changes:
            memory.content = changes["content"]
            memory.embedding = get_embedding_provider(get_settings()).embed_text(
                memory.content
            )
        for field in ("importance", "confidence", "structured_data", "valid_until"):
            if field in changes:
                setattr(memory, field, changes[field])
        if "status" in changes:
            memory.status = changes["status"].value
        session.flush()
        session.commit()
        result = LongTermMemoryResult(
            memory_id=memory.id,
            memory_type=memory.memory_type,
            content=memory.content,
            importance=memory.importance,
            source=memory.source,
            tags=memory.tags,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            namespace=memory.namespace,
            subject_id=memory.subject_id,
            memory_subtype=memory.memory_subtype,
            structured_data=memory.structured_data,
            confidence=memory.confidence,
            status=memory.status,
            source_type=memory.source_type,
            supersedes_id=memory.supersedes_id,
            valid_from=memory.valid_from,
            valid_until=memory.valid_until,
            last_accessed_at=memory.last_accessed_at,
            access_count=memory.access_count,
        )
        return _to_response(result)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()


@router.delete("/long-term/{memory_id}", status_code=204)
def delete_long_term_memory_endpoint(memory_id: uuid.UUID) -> None:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        if not soft_delete_memory(session, memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()


@router.get("/long-term/search", response_model=LongTermMemoryListResponse)
def search_long_term_memories_endpoint(
    keyword: str = Query(...),
    memory_type: str | None = None,
    min_importance: int | None = Query(
        default=None, ge=MIN_IMPORTANCE, le=MAX_IMPORTANCE
    ),
    limit: int = Query(
        default=DEFAULT_LIST_LIMIT, ge=MIN_LIST_LIMIT, le=MAX_LIST_LIMIT
    ),
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
            raise HTTPException(
                status_code=503, detail="Database is unavailable"
            ) from exc
    finally:
        session.close()

    responses = [_to_response(memory) for memory in memories]
    return LongTermMemoryListResponse(memories=responses, total=len(responses))
