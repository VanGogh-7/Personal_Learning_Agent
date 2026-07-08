import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.learning_events.constants import (
    EVENT_BOOK_RAG_QUESTION_ASKED,
    EVENT_MULTI_BOOK_RAG_QUESTION_ASKED,
    SOURCE_RAG,
)
from app.learning_events.service import create_learning_event
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
    retrieve_relevant_chunks_for_library_items,
)
from app.rag.schemas import (
    LibraryItemRagQueryRequest,
    LibraryItemRagQueryResponse,
    MemoryMetadata,
    MultiBookRagQueryRequest,
    MultiBookRagQueryResponse,
    RagCitation,
    RagLibraryItemMetadata,
    RagQueryRequest,
    RagQueryResponse,
    RetrievedChunk,
    SelectedLibraryItemRead,
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
            create_learning_event(
                db_session,
                event_type=EVENT_BOOK_RAG_QUESTION_ASKED,
                title=f"Asked question about: {library_item.title}",
                source_type=SOURCE_RAG,
                source_id=library_item.item_id,
                library_item_id=library_item.item_id,
                session_id=session_id,
                metadata_json={
                    "question": request.question,
                    "total_retrieved": len(retrieved),
                    "citation_count": len(retrieved),
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


@router.post("/query/library-items", response_model=MultiBookRagQueryResponse)
def rag_query_library_items_endpoint(
    request: MultiBookRagQueryRequest,
) -> MultiBookRagQueryResponse:
    session_id = request.session_id or create_session_id()
    try:
        library_item_ids = [uuid.UUID(item_id) for item_id in request.library_item_ids]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="library_item_ids must contain valid UUIDs"
        ) from exc

    try:
        db_session = get_db_session()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    long_term_memories: list = []
    try:
        try:
            selected_items, retrieved = retrieve_relevant_chunks_for_library_items(
                db_session,
                library_item_ids=library_item_ids,
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
                library_item_context=_build_library_items_context(selected_items),
            )
            save_turn(
                db_session,
                session_id,
                request.question,
                answer,
                metadata={
                    "query_type": "multi_book_rag",
                    "scope": "library_items",
                    "library_item_ids": [str(item.item_id) for item in selected_items],
                    "retrieved_chunk_ids": [str(chunk.chunk_id) for chunk in retrieved],
                    "citation_count": len(retrieved),
                },
            )
            create_learning_event(
                db_session,
                event_type=EVENT_MULTI_BOOK_RAG_QUESTION_ASKED,
                title="Asked question across selected books",
                source_type=SOURCE_RAG,
                session_id=session_id,
                metadata_json={
                    "question": request.question,
                    "library_item_ids": [str(item.item_id) for item in selected_items],
                    "library_titles": [item.title for item in selected_items],
                    "total_retrieved": len(retrieved),
                    "citation_count": len(retrieved),
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

    return MultiBookRagQueryResponse(
        answer=answer,
        selected_library_items=[
            SelectedLibraryItemRead(
                id=str(item.item_id),
                title=item.title,
                author=item.author,
                file_type=item.file_type,
                status=item.status,
            )
            for item in selected_items
        ],
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


def _build_library_items_context(selected_items: list) -> str:
    lines = ["Selected books:"]
    for index, item in enumerate(selected_items, start=1):
        parts = [f"{index}. {item.title}", f"status: {item.status}"]
        if item.author:
            parts.append(f"author: {item.author}")
        if item.file_type:
            parts.append(f"file type: {item.file_type}")
        lines.append("; ".join(parts))
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
        page_number=citation.page_number,
        page_start=citation.page_start,
        page_end=citation.page_end,
        section_type=citation.section_type,
        chapter_title=citation.chapter_title,
        section_title=citation.section_title,
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
            page_number=citation.page_number,
            page_start=item.page_start,
            page_end=item.page_end,
            section_type=item.section_type,
            chapter_title=item.chapter_title,
            section_title=item.section_title,
            content=item.content,
            char_start=item.char_start,
            char_end=item.char_end,
            score=item.score,
            citation=citation,
        )
        for item, citation in zip(retrieved, citations)
    ]
