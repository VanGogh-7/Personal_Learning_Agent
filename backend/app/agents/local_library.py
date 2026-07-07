import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.memory.long_term import LongTermMemoryResult
from app.memory.short_term import ConversationTurnResult
from app.rag.citations import ChunkCitationResult, build_chunk_citations
from app.rag.qa import build_deterministic_answer
from app.rag.retrieval import (
    LibraryItemRagContext,
    RetrievedChunkResult,
    retrieve_relevant_chunks,
    retrieve_relevant_chunks_for_library_item,
    retrieve_relevant_chunks_for_library_items,
)


GlobalRetrieve = Callable[[Session, str, int], list[RetrievedChunkResult]]
SingleBookRetrieve = Callable[
    [Session, uuid.UUID, str, int],
    tuple[LibraryItemRagContext, list[RetrievedChunkResult]],
]
MultiBookRetrieve = Callable[
    [Session, list[uuid.UUID], str, int],
    tuple[list[LibraryItemRagContext], list[RetrievedChunkResult]],
]
LocalLibraryScope = Literal["global", "single_book", "multi_book"]


@dataclass(frozen=True)
class LocalLibraryAgentResult:
    summary: str
    selected_library_items: list[LibraryItemRagContext]
    retrieved_chunks: list[RetrievedChunkResult]
    citations: list[ChunkCitationResult]


def run_local_library_agent(
    session: Session,
    *,
    question: str,
    scope_type: LocalLibraryScope,
    library_item_id: str | None,
    library_item_ids: list[str],
    top_k: int,
    recent_turns: list[ConversationTurnResult] | None = None,
    long_term_memories: list[LongTermMemoryResult] | None = None,
    retrieve_global: GlobalRetrieve = retrieve_relevant_chunks,
    retrieve_single_book: SingleBookRetrieve = retrieve_relevant_chunks_for_library_item,
    retrieve_multi_book: MultiBookRetrieve = retrieve_relevant_chunks_for_library_items,
) -> LocalLibraryAgentResult:
    """Search indexed local Library content and build page-aware evidence."""
    selected_items: list[LibraryItemRagContext]

    if scope_type == "single_book":
        if library_item_id is None:
            raise ValueError("library_item_id is required for single_book scope")
        selected_item, retrieved = retrieve_single_book(
            session,
            uuid.UUID(library_item_id),
            question,
            top_k,
        )
        selected_items = [selected_item]
    elif scope_type == "multi_book":
        selected_items, retrieved = retrieve_multi_book(
            session,
            [uuid.UUID(item_id) for item_id in library_item_ids],
            question,
            top_k,
        )
    else:
        selected_items = []
        retrieved = retrieve_global(session, question, top_k)

    citations = build_chunk_citations(retrieved)
    summary = build_deterministic_answer(
        question,
        retrieved,
        recent_turns=recent_turns,
        long_term_memories=long_term_memories,
    )
    return LocalLibraryAgentResult(
        summary=summary,
        selected_library_items=selected_items,
        retrieved_chunks=retrieved,
        citations=citations,
    )
