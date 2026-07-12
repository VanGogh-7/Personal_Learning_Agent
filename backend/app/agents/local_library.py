import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.memory.long_term import LongTermMemoryResult
from app.memory.short_term import ConversationTurnResult
from app.rag.citations import ChunkCitationResult, build_chunk_citations
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
EvidenceQuality = Literal["strong", "partial", "weak", "none"]


@dataclass(frozen=True)
class LocalLibraryAgentResult:
    summary: str
    selected_library_items: list[LibraryItemRagContext]
    retrieved_chunks: list[RetrievedChunkResult]
    citations: list[ChunkCitationResult]
    evidence_quality: EvidenceQuality


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
    summary = _build_evidence_summary(retrieved, citations)
    return LocalLibraryAgentResult(
        summary=summary,
        selected_library_items=selected_items,
        retrieved_chunks=retrieved,
        citations=citations,
        evidence_quality=classify_evidence_quality(retrieved),
    )


def classify_evidence_quality(
    retrieved_chunks: list[RetrievedChunkResult],
) -> EvidenceQuality:
    """Classify local evidence using only already-computed retrieval scores."""
    if not retrieved_chunks:
        return "none"

    best_score = min(chunk.score for chunk in retrieved_chunks)
    if best_score <= 0.15:
        return "strong"
    if best_score <= 0.35:
        return "partial"
    return "weak"


def _build_evidence_summary(
    chunks: list[RetrievedChunkResult], citations: list[ChunkCitationResult]
) -> str:
    """Return bounded findings for Synthesis, never a second complete answer."""
    if not chunks:
        return "No relevant local Library evidence was retrieved."
    lines = ["Local Library evidence:"]
    for chunk, citation in zip(chunks, citations, strict=True):
        excerpt = " ".join(chunk.content.split())[:800]
        lines.append(f"[{citation.citation_id}] {excerpt}")
    return "\n".join(lines)
