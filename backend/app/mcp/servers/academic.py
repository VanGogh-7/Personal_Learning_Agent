from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

from app.mcp.academic_api import AcademicApiClient

_client: AcademicApiClient | None = None


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict[str, Any]]:
    global _client
    _client = AcademicApiClient()
    try:
        yield {"academic_client": _client}
    finally:
        await _client.close()
        _client = None


mcp = FastMCP("PLA Academic Research", lifespan=lifespan, json_response=True)


def client() -> AcademicApiClient:
    if _client is None:
        raise RuntimeError("Academic MCP is not ready")
    return _client


@mcp.tool(name="search_arxiv", structured_output=True)
async def search_arxiv(query: str, limit: int = 5) -> dict[str, Any]:
    """Search arXiv metadata without downloading paper PDFs."""
    return {"items": await client().search_arxiv(query, limit)}


@mcp.tool(name="search_openalex", structured_output=True)
async def search_openalex(query: str, limit: int = 5) -> dict[str, Any]:
    """Search OpenAlex works and normalized metadata."""
    return {"items": await client().search_openalex(query, limit)}


@mcp.tool(name="lookup_doi", structured_output=True)
async def lookup_doi(doi: str) -> dict[str, Any]:
    """Look up one DOI using Crossref metadata."""
    return {"items": [await client().lookup_doi(doi)]}


@mcp.tool(name="get_paper_metadata", structured_output=True)
async def get_paper_metadata(identifier: str) -> dict[str, Any]:
    """Get metadata for one DOI or arXiv identifier."""
    return {"items": [await client().get_paper_metadata(identifier)]}


if __name__ == "__main__":
    mcp.run(transport="stdio")
