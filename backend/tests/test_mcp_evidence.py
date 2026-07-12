from app.agents.web_research import WebSourceResult
from app.graphs.schemas import WebSource
from app.mcp.evidence import canonicalize_url, deduplicate_and_rank, normalize_evidence


def test_normalize_academic_evidence_and_assign_web_citations() -> None:
    normalized = normalize_evidence(
        {
            "items": [
                {
                    "title": "Closed Graph Theorem",
                    "url": "https://arxiv.org/abs/1234.5678",
                    "abstract": "A proof for Banach spaces.",
                    "authors": ["Ada", "Emmy"],
                    "doi": "10.1000/example",
                    "arxiv_id": "1234.5678",
                }
            ]
        },
        provider="academic",
        source_type="academic",
    )
    ranked, removed = deduplicate_and_rank(normalized, prefer_academic=True, limit=5)
    assert removed == 0
    assert ranked[0].source_id == "W1"
    assert ranked[0].source_type == "academic"
    assert ranked[0].authors == ("Ada", "Emmy")
    assert ranked[0].evidence_id


def test_url_and_similar_content_deduplication() -> None:
    first = WebSourceResult(
        source_id="",
        title="Same result",
        url="https://Example.com/page/?utm_source=test",
        excerpt="The same useful evidence about Banach spaces.",
        provider="tavily",
    )
    second = WebSourceResult(
        source_id="",
        title="Same result",
        url="https://example.com/page",
        excerpt="The same useful evidence about Banach spaces.",
        provider="brave",
    )
    ranked, removed = deduplicate_and_rank(
        [first, second], prefer_academic=False, limit=5
    )
    assert len(ranked) == 1
    assert removed == 1
    assert canonicalize_url(first.url) == canonicalize_url(second.url)


def test_academic_web_source_schema_preserves_w_marker_metadata() -> None:
    source = WebSource(
        source_id="W1",
        title="Paper",
        url="https://doi.org/10.1000/test",
        excerpt="Evidence",
        provider="academic",
        source_type="academic",
        authors=["Ada"],
        doi="10.1000/test",
    )
    assert source.source_id == "W1"
    assert source.source_type == "academic"
    assert source.doi == "10.1000/test"
