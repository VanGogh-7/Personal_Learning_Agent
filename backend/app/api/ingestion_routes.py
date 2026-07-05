from fastapi import APIRouter, HTTPException

from app.ingestion.chunking import chunk_text
from app.ingestion.loaders import (
    DataFileNotFoundError,
    PathTraversalError,
    UnsupportedFileTypeError,
    load_text_file,
)
from app.ingestion.schemas import (
    ChunkTextRequest,
    ChunkTextResponse,
    LoadFileRequest,
    LoadFileResponse,
)

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


@router.post("/chunk-text", response_model=ChunkTextResponse)
def chunk_text_endpoint(request: ChunkTextRequest) -> ChunkTextResponse:
    try:
        chunks = chunk_text(request.text, request.chunk_size, request.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ChunkTextResponse(chunks=chunks, total_chunks=len(chunks))


@router.post("/load-file", response_model=LoadFileResponse)
def load_file_endpoint(request: LoadFileRequest) -> LoadFileResponse:
    try:
        text = load_text_file(request.file_path)
    except (PathTraversalError, UnsupportedFileTypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DataFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        chunks = chunk_text(text, request.chunk_size, request.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return LoadFileResponse(
        file_path=request.file_path, chunks=chunks, total_chunks=len(chunks)
    )
