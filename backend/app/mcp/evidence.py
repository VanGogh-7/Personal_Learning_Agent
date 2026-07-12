from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from time import perf_counter
from typing import Any, Iterable, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.agents.web_research import WebSourceResult
from app.observability.latency import current_latency_trace

SourceType = Literal["web", "news", "academic", "page"]
TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_")


def normalize_evidence(
    payload: dict[str, Any] | list[Any],
    *,
    provider: str,
    source_type: SourceType,
) -> list[WebSourceResult]:
    started_at = perf_counter()
    items = _candidate_items(payload)
    evidence: list[WebSourceResult] = []
    for item in items:
        title = _text(item, "title", "name", "display_name")
        url = _text(item, "url", "link", "landing_page_url", "id")
        excerpt = _text(
            item,
            "excerpt",
            "content",
            "snippet",
            "description",
            "abstract",
            "abstract_text",
        )
        if not title or not url or not excerpt:
            continue
        normalized_url = canonicalize_url(url)
        if not normalized_url:
            continue
        authors = _authors(item.get("authors") or item.get("authorships"))
        doi = _normalize_doi(
            _text(item, "doi", "DOI") or _nested_text(item, "ids", "doi")
        )
        arxiv_id = _text(item, "arxiv_id") or _arxiv_id_from_url(normalized_url)
        published = _text(
            item,
            "published_at",
            "published_date",
            "published",
            "publication_date",
            "created_date",
        )
        evidence.append(
            WebSourceResult(
                source_id="",
                evidence_id=_evidence_id(provider, normalized_url),
                source_type=source_type,
                provider=provider,
                title=_clean_text(title, 300),
                url=normalized_url,
                excerpt=_clean_text(excerpt, 1_200),
                content=None,
                authors=authors,
                published_date=published or None,
                published_at=published or None,
                retrieved_at=retrieved_at_iso(),
                doi=doi,
                arxiv_id=arxiv_id,
            )
        )
    trace = current_latency_trace()
    if trace is not None:
        trace.record("mcp_normalize", (perf_counter() - started_at) * 1000)
    return evidence


def deduplicate_and_rank(
    values: Iterable[WebSourceResult],
    *,
    prefer_academic: bool,
    limit: int,
) -> tuple[list[WebSourceResult], int]:
    candidates = [value for value in values if value.url and value.excerpt]
    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if prefer_academic and item.source_type == "academic" else 1,
            _provider_priority(item.provider),
            -len(item.excerpt),
        ),
    )
    unique: list[WebSourceResult] = []
    seen_urls: set[str] = set()
    for item in ranked:
        canonical = canonicalize_url(item.url)
        if canonical in seen_urls:
            continue
        fingerprint = f"{item.title} {item.excerpt}".lower()
        if any(
            SequenceMatcher(
                None,
                fingerprint[:800],
                f"{existing.title} {existing.excerpt}".lower()[:800],
            ).ratio()
            >= 0.92
            for existing in unique
        ):
            continue
        seen_urls.add(canonical)
        unique.append(item)
        if len(unique) >= limit:
            break
    deduplicated_count = max(0, len(candidates) - len(unique))
    numbered = [
        replace(item, source_id=f"W{index}")
        for index, item in enumerate(unique, start=1)
    ]
    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter("evidence_count", len(numbered))
        trace.set_counter("deduplicated_count", deduplicated_count)
    return numbered, deduplicated_count


def attach_page_content(
    evidence: list[WebSourceResult], url: str, content: str
) -> list[WebSourceResult]:
    canonical = canonicalize_url(url)
    return [
        replace(item, content=content)
        if canonicalize_url(item.url) == canonical
        else item
        for item in evidence
    ]


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith(TRACKING_QUERY_PREFIXES)
        )
    )
    path = parsed.path.rstrip("/") or "/"
    netloc = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return ""
    if (
        port
        and not (parsed.scheme.lower() == "http" and port == 80)
        and not (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def _candidate_items(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    for key in ("items", "results", "papers", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    web = payload.get("web")
    if isinstance(web, dict) and isinstance(web.get("results"), list):
        return [item for item in web["results"] if isinstance(item, dict)]
    result = payload.get("result")
    if isinstance(result, dict):
        return _candidate_items(result)
    return [payload] if payload else []


def _text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_text(item: dict[str, Any], parent: str, key: str) -> str:
    value = item.get(parent)
    return _text(value, key) if isinstance(value, dict) else ""


def _authors(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for author in value:
        if isinstance(author, str):
            name = author.strip()
        elif isinstance(author, dict):
            name = _text(author, "name", "display_name")
            if not name and isinstance(author.get("author"), dict):
                name = _text(author["author"], "display_name", "name")
        else:
            name = ""
        if name and name not in names:
            names.append(name)
    return tuple(names[:20])


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _normalize_doi(value: str) -> str | None:
    normalized = value.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    return normalized or None


def _arxiv_id_from_url(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", url, re.IGNORECASE)
    return match.group(1).removesuffix(".pdf") if match else None


def _evidence_id(provider: str, url: str) -> str:
    digest = hashlib.sha256(f"{provider}:{url}".encode()).hexdigest()[:16]
    return f"evidence-{digest}"


def _provider_priority(provider: str) -> int:
    return {"academic": 0, "tavily": 1, "brave": 2, "fetch": 3}.get(provider, 9)


def retrieved_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
