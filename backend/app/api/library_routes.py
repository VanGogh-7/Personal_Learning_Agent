import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.learning_events.constants import (
    EVENT_LIBRARY_INDEXED,
    EVENT_METADATA_DRAFT_GENERATED,
    SOURCE_LIBRARY,
)
from app.learning_events.service import create_learning_event
from app.library.indexing import (
    LibraryIndexResult,
    LibraryIndexingError,
    index_library_item,
)
from app.library.importing import LibraryImportError, import_pdf_paths
from app.library.metadata_generation import (
    LibraryMetadataDraftResult,
    LibraryMetadataGenerationError,
    generate_library_metadata_draft,
)
from app.library.schemas import (
    LibraryItemCreate,
    LibraryItemIndexResponse,
    LibraryItemListResponse,
    LibraryItemRead,
    LibraryItemUpdate,
    LibraryMetadataDraftResponse,
    LibraryPdfImportItemResponse,
    LibraryPdfImportRequest,
    LibraryPdfImportResponse,
)
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


def _to_index_response(result: LibraryIndexResult) -> LibraryItemIndexResponse:
    return LibraryItemIndexResponse(
        item_id=str(result.item_id),
        document_id=str(result.document_id) if result.document_id else None,
        status=result.status,
        chunks_created=result.chunks_created,
        embeddings_created=result.embeddings_created,
        message=result.message,
    )


def _to_metadata_draft_response(
    result: LibraryMetadataDraftResult,
) -> LibraryMetadataDraftResponse:
    return LibraryMetadataDraftResponse(
        library_item_id=str(result.library_item_id),
        title=result.title,
        summary=result.summary,
        topic_tags=result.topic_tags,
        chunks_used=result.chunks_used,
        mode=result.mode,
    )


def _to_import_item_response(result) -> LibraryPdfImportItemResponse:
    return LibraryPdfImportItemResponse(
        library_item=_to_response(result.item),
        index_result=_to_index_response(result.index_result),
        original_filename=result.original_filename,
        original_source_path=result.original_source_path,
        managed_file_path=result.managed_file_path,
        file_size_bytes=result.file_size_bytes,
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


@router.post("/import-pdfs", response_model=LibraryPdfImportResponse)
def import_pdfs_endpoint(request: LibraryPdfImportRequest) -> LibraryPdfImportResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            results = import_pdf_paths(session, request.source_paths)
            for result in results:
                create_learning_event(
                    session,
                    event_type=EVENT_LIBRARY_INDEXED,
                    title=f"Imported and indexed PDF: {result.item.title}",
                    source_type=SOURCE_LIBRARY,
                    source_id=result.item.item_id,
                    library_item_id=result.item.item_id,
                    metadata_json={
                        "original_filename": result.original_filename,
                        "managed_file_path": result.managed_file_path,
                        "file_size_bytes": result.file_size_bytes,
                        "chunks_created": result.index_result.chunks_created,
                        "embeddings_created": result.index_result.embeddings_created,
                        "document_id": str(result.index_result.document_id)
                        if result.index_result.document_id
                        else None,
                    },
                )
            session.commit()
        except (LibraryImportError, LibraryIndexingError) as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    responses = [_to_import_item_response(result) for result in results]
    return LibraryPdfImportResponse(items=responses, total=len(responses))


@router.post("/items/{item_id}/index", response_model=LibraryItemIndexResponse)
def index_library_item_endpoint(item_id: uuid.UUID) -> LibraryItemIndexResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            result = index_library_item(session, item_id)
            if result is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Library item not found")
            item = get_library_item(session, item_id)
            if item is not None:
                create_learning_event(
                    session,
                    event_type=EVENT_LIBRARY_INDEXED,
                    title=f"Indexed library item: {item.title}",
                    source_type=SOURCE_LIBRARY,
                    source_id=item.item_id,
                    library_item_id=item.item_id,
                    metadata_json={
                        "chunks_created": result.chunks_created,
                        "embeddings_created": result.embeddings_created,
                        "document_id": str(result.document_id)
                        if result.document_id
                        else None,
                    },
                )
            session.commit()
        except HTTPException:
            raise
        except LibraryIndexingError as exc:
            session.commit()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_index_response(result)


@router.post("/items/{item_id}/metadata-draft", response_model=LibraryMetadataDraftResponse)
def generate_library_metadata_draft_endpoint(
    item_id: uuid.UUID,
) -> LibraryMetadataDraftResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            result = generate_library_metadata_draft(
                session,
                item_id,
            )
            if result is None:
                session.rollback()
                raise HTTPException(status_code=404, detail="Library item not found")
            create_learning_event(
                session,
                event_type=EVENT_METADATA_DRAFT_GENERATED,
                title=f"Generated metadata draft: {result.title}",
                source_type=SOURCE_LIBRARY,
                source_id=result.library_item_id,
                library_item_id=result.library_item_id,
                metadata_json={
                    "chunks_used": result.chunks_used,
                    "topic_tags_count": len(result.topic_tags),
                    "mode": result.mode,
                },
            )
            session.commit()
        except HTTPException:
            raise
        except LibraryMetadataGenerationError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    return _to_metadata_draft_response(result)


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
