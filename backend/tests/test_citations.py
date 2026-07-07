import uuid

from app.rag.citations import build_chunk_citations, make_excerpt
from app.rag.retrieval import RetrievedChunkResult


def _chunk(
    content: str,
    index: int = 0,
    page_start: int | None = None,
    page_end: int | None = None,
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


def test_build_chunk_citations_includes_page_metadata_when_available() -> None:
    chunk = _chunk("A compact set is closed and bounded.", page_start=12, page_end=12)

    citation = build_chunk_citations([chunk])[0]

    assert citation.page_number == 12
    assert citation.page_start == 12
    assert citation.page_end == 12
