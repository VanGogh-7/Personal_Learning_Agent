from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.rag.qa import generate_answer
from app.rag.retrieval import retrieve_relevant_chunks
from app.rag.schemas import RagQueryRequest, RagQueryResponse, RetrievedChunk

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def rag_query_endpoint(request: RagQueryRequest) -> RagQueryResponse:
    try:
        session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        try:
            retrieved = retrieve_relevant_chunks(session, request.question, top_k=request.top_k)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        session.close()

    answer = generate_answer(request.question, retrieved)

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id=str(item.chunk_id),
            document_id=str(item.document_id),
            document_title=item.document_title,
            chunk_index=item.chunk_index,
            content=item.content,
            char_start=item.char_start,
            char_end=item.char_end,
            score=item.score,
        )
        for item in retrieved
    ]

    return RagQueryResponse(
        answer=answer,
        retrieved_chunks=retrieved_chunks,
        total_retrieved=len(retrieved_chunks),
    )
