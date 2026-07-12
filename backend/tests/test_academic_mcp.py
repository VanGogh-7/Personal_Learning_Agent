import httpx
import pytest

from app.core.config import Settings
from app.mcp.academic_api import AcademicApiClient, normalize_doi


ARXIV_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>https://arxiv.org/abs/1234.5678</id><title>Closed Graph</title>
  <summary>A theorem.</summary><published>2025-01-02T00:00:00Z</published>
  <author><name>Ada Lovelace</name></author></entry>
</feed>"""


@pytest.mark.anyio
async def test_academic_arxiv_openalex_and_doi_normalization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "arxiv.org" in request.url.host:
            return httpx.Response(200, text=ARXIV_XML)
        if "openalex.org" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "display_name": "OpenAlex Paper",
                            "authorships": [
                                {"author": {"display_name": "Emmy Noether"}}
                            ],
                            "abstract_inverted_index": {"Useful": [0], "paper": [1]},
                            "primary_location": {
                                "landing_page_url": "https://example.org/paper"
                            },
                            "ids": {"doi": "https://doi.org/10.1000/openalex"},
                            "publication_date": "2025-02-03",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "message": {
                    "title": ["Crossref Paper"],
                    "author": [{"given": "Alan", "family": "Turing"}],
                    "abstract": "<jats:p>Metadata abstract.</jats:p>",
                    "URL": "https://doi.org/10.1000/test",
                    "DOI": "10.1000/test",
                    "published-online": {"date-parts": [[2025, 3, 4]]},
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(academic_api_min_interval_seconds=0)
    client = AcademicApiClient(settings, http_client)
    arxiv = await client.search_arxiv("closed graph")
    metadata = await client.get_paper_metadata("1234.5678")
    openalex = await client.search_openalex("closed graph")
    crossref = await client.lookup_doi("https://doi.org/10.1000/TEST")
    assert arxiv[0]["arxiv_id"] == "1234.5678"
    assert metadata["title"] == "Closed Graph"
    assert openalex[0]["abstract"] == "Useful paper"
    assert crossref["doi"] == "10.1000/test"
    assert normalize_doi("doi:10.1000/TEST") == "10.1000/test"
    await http_client.aclose()
