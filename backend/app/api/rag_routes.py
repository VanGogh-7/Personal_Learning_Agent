from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.memory.long_term import DEFAULT_CONTEXT_MEMORY_COUNT, search_memories
from app.memory.short_term import (
    DEFAULT_RECENT_TURNS_LIMIT,
    create_session_id,
    get_recent_turns,
    save_turn,
)
from app.rag.qa import generate_answer
from app.rag.retrieval import retrieve_relevant_chunks
from app.rag.schemas import MemoryMetadata, RagQueryRequest, RagQueryResponse, RetrievedChunk

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def rag_query_endpoint(request: RagQueryRequest) -> RagQueryResponse:
    session_id = request.session_id or create_session_id()

    try:
        db_session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    long_term_memories: list = []
    try:
        try:
            retrieved = retrieve_relevant_chunks(db_session, request.question, top_k=request.top_k)
            recent_turns = get_recent_turns(
                db_session, session_id, limit=DEFAULT_RECENT_TURNS_LIMIT
            )
            if request.include_long_term_memory:
                long_term_memories = search_memories(
                    db_session, keyword=request.question, limit=DEFAULT_CONTEXT_MEMORY_COUNT
                )
            answer = generate_answer(
                request.question,
                retrieved,
                recent_turns=recent_turns,
                long_term_memories=long_term_memories,
            )
            save_turn(db_session, session_id, request.question, answer)
            db_session.commit()
        except SQLAlchemyError as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        db_session.close()

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
        session_id=session_id,
        memory=MemoryMetadata(
            used_recent_turns=len(recent_turns),
            saved_current_turn=True,
            used_long_term_memories=len(long_term_memories),
        ),
    )
