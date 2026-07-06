import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.llm.providers import LLMConfigurationError, LLMProviderError
from app.memory.long_term import DEFAULT_CONTEXT_MEMORY_COUNT, search_memories
from app.memory.short_term import (
    DEFAULT_RECENT_TURNS_LIMIT,
    create_session_id,
    get_recent_turns,
    save_turn,
)
from app.rag.citations import ChunkCitationResult, build_chunk_citations
from app.rag.qa import generate_answer
from app.rag.retrieval import (
    LibraryItemRagError,
    RetrievedChunkResult,
    retrieve_relevant_chunks,
    retrieve_relevant_chunks_for_library_item,
)
from app.rag.schemas import (
    LibraryItemRagQueryRequest,
    LibraryItemRagQueryResponse,
    MemoryMetadata,
    RagCitation,
    RagLibraryItemMetadata,
    RagQueryRequest,
    RagQueryResponse,
    RetrievedChunk,
)

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
        except (LLMConfigurationError, LLMProviderError) as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        db_session.close()

    citation_results = build_chunk_citations(retrieved)
    citations = [_citation_response(citation) for citation in citation_results]
    retrieved_chunks = _retrieved_chunk_responses(retrieved, citations)

    return RagQueryResponse(
        answer=answer,
        retrieved_chunks=retrieved_chunks,
        citations=citations,
        total_retrieved=len(retrieved_chunks),
        session_id=session_id,
        memory=MemoryMetadata(
            used_recent_turns=len(recent_turns),
            saved_current_turn=True,
            used_long_term_memories=len(long_term_memories),
        ),
    )


@router.post("/query/library-item", response_model=LibraryItemRagQueryResponse)
def rag_query_library_item_endpoint(
    request: LibraryItemRagQueryRequest,
) -> LibraryItemRagQueryResponse:
    session_id = request.session_id or create_session_id()
    try:
        library_item_id = uuid.UUID(request.library_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="library_item_id must be a valid UUID") from exc

    try:
        db_session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    long_term_memories: list = []
    try:
        try:
            library_item, retrieved = retrieve_relevant_chunks_for_library_item(
                db_session,
                library_item_id=library_item_id,
                question=request.question,
                top_k=request.top_k,
            )
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
                library_item_context=_build_library_item_context(
                    title=library_item.title,
                    author=library_item.author,
                    file_type=library_item.file_type,
                    status=library_item.status,
                ),
            )
            save_turn(
                db_session,
                session_id,
                request.question,
                answer,
                metadata={
                    "scope": "library_item",
                    "library_item_id": str(library_item.item_id),
                },
            )
            db_session.commit()
        except LibraryItemRagError as exc:
            db_session.rollback()
            detail = str(exc)
            status_code = 404 if detail == "Library item not found" else 400
            raise HTTPException(status_code=status_code, detail=detail) from exc
        except SQLAlchemyError as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
        except (LLMConfigurationError, LLMProviderError) as exc:
            db_session.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        db_session.close()

    citation_results = build_chunk_citations(retrieved)
    citations = [_citation_response(citation) for citation in citation_results]
    retrieved_chunks = _retrieved_chunk_responses(retrieved, citations)

    return LibraryItemRagQueryResponse(
        answer=answer,
        library_item=RagLibraryItemMetadata(
            id=str(library_item.item_id),
            title=library_item.title,
            author=library_item.author,
            file_type=library_item.file_type,
            status=library_item.status,
        ),
        retrieved_chunks=retrieved_chunks,
        citations=citations,
        total_retrieved=len(retrieved_chunks),
        session_id=session_id,
        memory=MemoryMetadata(
            used_recent_turns=len(recent_turns),
            saved_current_turn=True,
            used_long_term_memories=len(long_term_memories),
        ),
    )


def _build_library_item_context(
    *, title: str, author: str | None, file_type: str | None, status: str
) -> str:
    lines = [f"Title: {title}", f"Status: {status}"]
    if author:
        lines.append(f"Author: {author}")
    if file_type:
        lines.append(f"File type: {file_type}")
    return "\n".join(lines)


def _citation_response(citation: ChunkCitationResult) -> RagCitation:
    return RagCitation(
        citation_id=citation.citation_id,
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        library_item_id=citation.library_item_id,
        library_title=citation.library_title,
        library_author=citation.library_author,
        document_title=citation.document_title,
        document_source_path=citation.document_source_path,
        chunk_index=citation.chunk_index,
        score=citation.score,
        excerpt=citation.excerpt,
        content=citation.content,
    )


def _retrieved_chunk_responses(
    retrieved: list[RetrievedChunkResult],
    citations: list[RagCitation],
) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=str(item.chunk_id),
            document_id=str(item.document_id),
            document_title=item.document_title,
            document_source_path=item.document_source_path,
            chunk_index=item.chunk_index,
            content=item.content,
            char_start=item.char_start,
            char_end=item.char_end,
            score=item.score,
            citation=citation,
        )
        for item, citation in zip(retrieved, citations)
    ]
