import re
from dataclasses import dataclass

from app.rag.retrieval import RetrievedChunkResult

DEFAULT_EXCERPT_LENGTH = 240


@dataclass(frozen=True)
class ChunkCitationResult:
    citation_id: str
    chunk_id: str
    document_id: str
    library_item_id: str | None
    library_title: str | None
    library_author: str | None
    document_title: str | None
    document_source_path: str | None
    chunk_index: int
    page_number: int | None
    page_start: int | None
    page_end: int | None
    score: float
    excerpt: str
    content: str
    section_type: str = "unknown"
    chapter_title: str | None = None
    section_title: str | None = None


def make_excerpt(text: str, max_length: int = DEFAULT_EXCERPT_LENGTH) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""
    if len(normalized) <= max_length:
        return normalized

    if max_length <= 3:
        return "." * max_length
    return f"{normalized[: max_length - 3].rstrip()}..."


def build_chunk_citations(
    retrieved_chunks: list[RetrievedChunkResult],
    max_excerpt_length: int = DEFAULT_EXCERPT_LENGTH,
) -> list[ChunkCitationResult]:
    citations: list[ChunkCitationResult] = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        # Local Library evidence always uses S-prefixed source IDs; web sources
        # use W-prefixed IDs and are kept separate by the agent response schema.
        citations.append(
            ChunkCitationResult(
                citation_id=f"S{index}",
                chunk_id=str(chunk.chunk_id),
                document_id=str(chunk.document_id),
                library_item_id=str(chunk.library_item_id) if chunk.library_item_id else None,
                library_title=chunk.library_title,
                library_author=chunk.library_author,
                document_title=chunk.document_title,
                document_source_path=chunk.document_source_path,
                chunk_index=chunk.chunk_index,
                page_number=_single_page_number(chunk.page_start, chunk.page_end),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_type=chunk.section_type,
                chapter_title=chunk.chapter_title,
                section_title=chunk.section_title,
                score=chunk.score,
                excerpt=make_excerpt(chunk.content, max_length=max_excerpt_length),
                content=chunk.content,
            )
        )
    return citations


def format_page_range(
    page_start: int | None,
    page_end: int | None,
    page_number: int | None = None,
) -> str:
    if page_number is not None:
        return f"p. {page_number}"
    if page_start is not None and page_end is not None:
        if page_start == page_end:
            return f"p. {page_start}"
        return f"pp. {page_start}-{page_end}"
    if page_start is not None:
        return f"p. {page_start}"
    if page_end is not None:
        return f"p. {page_end}"
    return "page unknown"


def format_citation_source(
    citation: ChunkCitationResult,
    *,
    include_score: bool = True,
) -> str:
    title = citation.library_title or citation.document_title or citation.document_id
    parts = [
        f"[{citation.citation_id}]",
        str(title),
        format_page_range(citation.page_start, citation.page_end, citation.page_number),
        f"chunk {citation.chunk_index}",
    ]
    if citation.section_type:
        parts.append(f"section_type: {citation.section_type}")
    if citation.chapter_title:
        parts.append(f"chapter: {citation.chapter_title}")
    if citation.section_title:
        parts.append(f"section: {citation.section_title}")
    if include_score:
        parts.append(f"score: {citation.score:.4f}")
    return "; ".join(parts)


def _single_page_number(page_start: int | None, page_end: int | None) -> int | None:
    if page_start is not None and page_start == page_end:
        return page_start
    return None
