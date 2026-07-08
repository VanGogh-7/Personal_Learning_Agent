import uuid

from app.rag.citations import build_chunk_citations, format_citation_source, make_excerpt
from app.rag.retrieval import RetrievedChunkResult


def _chunk(
    content: str,
    index: int = 0,
    page_start: int | None = None,
    page_end: int | None = None,
    section_type: str = "body",
    chapter_title: str | None = None,
    section_title: str | None = None,
) -> RetrievedChunkResult:
    return RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Linear Algebra Notes",
        document_source_path="/tmp/linear-algebra.md",
        library_item_id=uuid.uuid4(),
        library_title="Linear Algebra",
        library_author="Some Author",
        chunk_index=index,
        content=content,
        char_start=0,
        char_end=len(content),
        page_start=page_start,
        page_end=page_end,
        section_type=section_type,
        chapter_title=chapter_title,
        section_title=section_title,
        score=0.123,
    )


def test_make_excerpt_normalizes_whitespace_and_truncates() -> None:
    excerpt = make_excerpt("  A vector\n\nspace\t over   a field has addition.  ", max_length=24)

    assert excerpt == "A vector space over a..."


def test_make_excerpt_handles_empty_content() -> None:
    assert make_excerpt(" \n\t ") == ""


def test_build_chunk_citations_assigns_deterministic_ids_and_metadata() -> None:
    first = _chunk("A vector space over a field.", index=0)
    second = _chunk("A linear map preserves addition.", index=1)

    citations = build_chunk_citations([first, second])

    assert [citation.citation_id for citation in citations] == ["S1", "S2"]
    assert citations[0].chunk_id == str(first.chunk_id)
    assert citations[0].document_id == str(first.document_id)
    assert citations[0].library_item_id == str(first.library_item_id)
    assert citations[0].library_title == "Linear Algebra"
    assert citations[0].library_author == "Some Author"
    assert citations[0].document_title == "Linear Algebra Notes"
    assert citations[0].document_source_path == "/tmp/linear-algebra.md"
    assert citations[0].chunk_index == 0
    assert citations[0].score == 0.123
    assert citations[0].excerpt == "A vector space over a field."
    assert citations[0].page_number is None
    assert citations[0].page_start is None
    assert citations[0].page_end is None
    assert citations[0].section_type == "body"
    assert citations[0].chapter_title is None
    assert citations[0].section_title is None


def test_build_chunk_citations_includes_page_metadata_when_available() -> None:
    chunk = _chunk(
        "A compact set is closed and bounded.",
        page_start=12,
        page_end=12,
        chapter_title="Chapter IV Metric Spaces",
        section_title="IV.3 Compactness",
    )

    citation = build_chunk_citations([chunk])[0]

    assert citation.page_number == 12
    assert citation.page_start == 12
    assert citation.page_end == 12
    assert citation.chapter_title == "Chapter IV Metric Spaces"
    assert citation.section_title == "IV.3 Compactness"


def test_format_citation_source_uses_normalized_id_and_metadata() -> None:
    chunk = _chunk(
        "Banach spaces are complete normed vector spaces.",
        index=4,
        page_start=20,
        page_end=22,
        section_type="body",
        chapter_title="Chapter V Normed Spaces",
        section_title="V.1 Banach Spaces",
    )

    citation = build_chunk_citations([chunk])[0]

    assert format_citation_source(citation) == (
        "[S1]; Linear Algebra; pp. 20-22; chunk 4; section_type: body; "
        "chapter: Chapter V Normed Spaces; section: V.1 Banach Spaces; score: 0.1230"
    )
