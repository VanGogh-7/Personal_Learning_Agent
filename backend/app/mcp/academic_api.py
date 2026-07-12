from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from time import monotonic
from typing import Any

import httpx

from app.core.config import Settings, get_settings

ARXIV_API = "https://export.arxiv.org/api/query"
OPENALEX_API = "https://api.openalex.org/works"
CROSSREF_API = "https://api.crossref.org/works"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


class AcademicApiClient:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.academic_api_timeout_seconds),
            headers={"User-Agent": self.settings.academic_api_user_agent},
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_arxiv(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        response = await self._get(
            ARXIV_API,
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": _limit(limit),
                "sortBy": "relevance",
            },
        )
        root = ET.fromstring(response.text)
        return [_arxiv_entry(entry) for entry in root.findall("atom:entry", ARXIV_NS)]

    async def search_openalex(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        response = await self._get(
            OPENALEX_API,
            params={"search": query, "per-page": _limit(limit)},
        )
        results = response.json().get("results", [])
        return [_openalex_work(item) for item in results if isinstance(item, dict)]

    async def lookup_doi(self, doi: str) -> dict[str, Any]:
        normalized = normalize_doi(doi)
        response = await self._get(f"{CROSSREF_API}/{normalized}")
        message = response.json().get("message", {})
        if not isinstance(message, dict):
            raise ValueError("Crossref returned invalid metadata")
        return _crossref_work(message)

    async def get_paper_metadata(self, identifier: str) -> dict[str, Any]:
        if identifier.lower().startswith("10.") or "doi.org/10." in identifier:
            return await self.lookup_doi(identifier)
        arxiv_id = identifier.rsplit("/", 1)[-1].removesuffix(".pdf")
        response = await self._get(
            ARXIV_API, params={"id_list": arxiv_id, "max_results": 1}
        )
        root = ET.fromstring(response.text)
        entry = root.find("atom:entry", ARXIV_NS)
        if entry is None:
            raise ValueError("Paper metadata was not found")
        return _arxiv_entry(entry)

    async def _get(
        self, url: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        async with self._rate_lock:
            remaining = self.settings.academic_api_min_interval_seconds - (
                monotonic() - self._last_request_at
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            response = await self._client.get(url, params=params)
            self._last_request_at = monotonic()
        response.raise_for_status()
        return response


def normalize_doi(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.removeprefix("https://doi.org/").removeprefix("doi:")
    if not re.fullmatch(r"10\.\d{4,9}/\S+", normalized):
        raise ValueError("Invalid DOI")
    return normalized.rstrip(".,;)")


def _arxiv_entry(entry: ET.Element) -> dict[str, Any]:
    identifier = _xml_text(entry, "atom:id").rsplit("/", 1)[-1]
    return {
        "title": _xml_text(entry, "atom:title"),
        "authors": [
            _xml_text(author, "atom:name")
            for author in entry.findall("atom:author", ARXIV_NS)
        ],
        "abstract": _xml_text(entry, "atom:summary"),
        "url": f"https://arxiv.org/abs/{identifier}",
        "arxiv_id": identifier,
        "doi": _xml_text(entry, "{http://arxiv.org/schemas/atom}doi") or None,
        "published_at": _xml_text(entry, "atom:published") or None,
    }


def _openalex_work(item: dict[str, Any]) -> dict[str, Any]:
    primary = item.get("primary_location") or {}
    ids = item.get("ids") or {}
    return {
        "title": item.get("display_name") or item.get("title") or "Untitled paper",
        "authors": [
            (authorship.get("author") or {}).get("display_name")
            for authorship in item.get("authorships", [])
            if isinstance(authorship, dict)
            and (authorship.get("author") or {}).get("display_name")
        ],
        "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
        "url": primary.get("landing_page_url") or ids.get("doi") or item.get("id"),
        "doi": (ids.get("doi") or "").removeprefix("https://doi.org/") or None,
        "arxiv_id": None,
        "published_at": item.get("publication_date"),
    }


def _crossref_work(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title") or []
    abstract = re.sub(r"<[^>]+>", " ", str(item.get("abstract") or ""))
    return {
        "title": titles[0] if titles else "Untitled paper",
        "authors": [
            " ".join(
                part for part in (author.get("given"), author.get("family")) if part
            )
            for author in item.get("author", [])
            if isinstance(author, dict)
        ],
        "abstract": re.sub(r"\s+", " ", abstract).strip()
        or "Crossref metadata record without an abstract.",
        "url": item.get("URL") or f"https://doi.org/{item.get('DOI', '')}",
        "doi": item.get("DOI"),
        "arxiv_id": None,
        "published_at": _crossref_date(item),
    }


def _openalex_abstract(value: Any) -> str:
    if not isinstance(value, dict):
        return "OpenAlex metadata record without an abstract."
    words: list[tuple[int, str]] = []
    for word, positions in value.items():
        if isinstance(positions, list):
            words.extend((int(position), str(word)) for position in positions)
    return " ".join(word for _, word in sorted(words))


def _crossref_date(item: dict[str, Any]) -> str | None:
    for key in ("published-print", "published-online", "created"):
        parts = (item.get(key) or {}).get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            return "-".join(str(value) for value in parts[0])
    return None


def _xml_text(entry: ET.Element, path: str) -> str:
    node = entry.find(path, ARXIV_NS)
    return re.sub(r"\s+", " ", node.text or "").strip() if node is not None else ""


def _limit(value: int) -> int:
    return max(1, min(int(value), 10))
