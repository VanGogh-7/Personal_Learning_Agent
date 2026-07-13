from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from app.agents.web_research import WebResearchResult, WebSourceResult
from app.core.config import Settings, get_settings
from app.mcp.client import MCPError
from app.mcp.evidence import (
    attach_page_content,
    deduplicate_and_rank,
    normalize_evidence,
)
from app.mcp.gateway import MCPToolGateway
from app.observability.latency import current_latency_trace

ActivityCallback = Callable[[str, str], None]
URL_PATTERN = re.compile(r"https?://[^\s<>\]\[()]+", re.IGNORECASE)
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class ResearchPlan:
    query: str
    urls: tuple[str, ...]
    academic: bool
    current_or_cross_check: bool
    doi: str | None


def plan_research(question: str) -> ResearchPlan:
    lowered = question.lower()
    urls = tuple(dict.fromkeys(URL_PATTERN.findall(question)))
    academic_terms = (
        "paper",
        "research",
        "arxiv",
        "doi",
        "journal",
        "theorem",
        "\u8bba\u6587",
        "\u6587\u732e",
        "\u5b66\u672f",
        "\u671f\u520a",
    )
    current_terms = (
        "latest",
        "current",
        "today",
        "recent",
        "news",
        "\u6700\u65b0",
        "\u5f53\u524d",
        "\u8fd1\u671f",
        "\u65b0\u95fb",
        "cross-check",
    )
    doi_match = DOI_PATTERN.search(question)
    return ResearchPlan(
        query=" ".join(question.strip().split()),
        urls=urls,
        academic=bool(doi_match) or any(term in lowered for term in academic_terms),
        current_or_cross_check=any(term in lowered for term in current_terms),
        doi=doi_match.group(0).rstrip(".,;)") if doi_match else None,
    )


async def run_mcp_research(
    question: str,
    *,
    gateway: MCPToolGateway | None = None,
    settings: Settings | None = None,
    activity: ActivityCallback | None = None,
) -> WebResearchResult:
    resolved_settings = settings or get_settings()
    resolved_gateway = gateway or MCPToolGateway(settings=resolved_settings)
    plan = plan_research(question)
    warnings: list[str] = []
    evidence: list[WebSourceResult] = []

    _activity(activity, "planning_web", "Searching the web")
    if plan.academic:
        _activity(activity, "searching_academic", "Searching academic sources")
        academic_results, academic_warnings = await _academic_search(
            plan, resolved_gateway
        )
        evidence.extend(academic_results)
        warnings.extend(academic_warnings)

    should_search_web = not plan.urls and (not plan.academic or not evidence)
    if should_search_web:
        _activity(activity, "searching_web", "Searching the web")
        web_results, web_warnings = await _web_search(plan, resolved_gateway)
        evidence.extend(web_results)
        warnings.extend(web_warnings)

    if plan.urls:
        evidence.extend(
            normalize_evidence(
                [
                    {
                        "title": url,
                        "url": url,
                        "excerpt": "User-selected public page.",
                    }
                    for url in plan.urls
                ],
                provider="fetch",
                source_type="page",
            )
        )

    evidence, _ = deduplicate_and_rank(
        evidence,
        prefer_academic=plan.academic,
        limit=resolved_settings.mcp_max_evidence,
    )
    fetch_targets = [item.url for item in evidence if item.url][
        : resolved_settings.mcp_max_fetch_urls
    ]
    if fetch_targets:
        _activity(activity, "reading_pages", "Evaluating sources")
        evidence, fetch_warnings = await _fetch_pages(
            evidence, fetch_targets, resolved_gateway, resolved_settings
        )
        warnings.extend(fetch_warnings)

    _activity(activity, "filtering_sources", "Evaluating sources")
    evidence, _ = deduplicate_and_rank(
        evidence,
        prefer_academic=plan.academic,
        limit=resolved_settings.mcp_max_evidence,
    )
    summary = (
        " ".join(
            f"[{item.source_id}] {item.title}: {(item.content or item.excerpt)[:500]}"
            for item in evidence
        )
        or None
    )
    status = "available" if evidence else "unavailable"
    if not evidence and not warnings:
        warnings.append("No usable web or academic evidence was returned.")
    return WebResearchResult(
        summary=summary,
        sources=evidence,
        status=status,
        warnings=_dedupe(warnings),
    )


async def run_mcp_web_research(
    question: str,
    *,
    gateway: MCPToolGateway,
    settings: Settings | None = None,
    activity: ActivityCallback | None = None,
) -> WebResearchResult:
    """Run only general-web MCP work for the adaptive Web subgraph."""
    resolved = settings or get_settings()
    plan = plan_research(question)
    _activity(activity, "searching_web", "Searching the web")
    evidence, warnings = await _web_search(plan, gateway)
    evidence, _ = deduplicate_and_rank(
        evidence, prefer_academic=False, limit=resolved.mcp_max_evidence
    )
    targets = [item.url for item in evidence if item.url][: resolved.mcp_max_fetch_urls]
    if targets:
        _activity(activity, "reading_pages", "Evaluating sources")
        evidence, fetch_warnings = await _fetch_pages(
            evidence, targets, gateway, resolved
        )
        warnings.extend(fetch_warnings)
    return _research_result(
        evidence, warnings, prefer_academic=False, settings=resolved
    )


async def run_mcp_academic_research(
    question: str,
    *,
    gateway: MCPToolGateway,
    settings: Settings | None = None,
    activity: ActivityCallback | None = None,
) -> WebResearchResult:
    """Run only academic metadata MCP work for the Academic subgraph."""
    resolved = settings or get_settings()
    plan = plan_research(question)
    _activity(activity, "searching_academic", "Searching academic sources")
    evidence, warnings = await _academic_search(plan, gateway)
    return _research_result(evidence, warnings, prefer_academic=True, settings=resolved)


def _research_result(
    evidence: list[WebSourceResult],
    warnings: list[str],
    *,
    prefer_academic: bool,
    settings: Settings,
) -> WebResearchResult:
    evidence, _ = deduplicate_and_rank(
        evidence,
        prefer_academic=prefer_academic,
        limit=settings.mcp_max_evidence,
    )
    summary = (
        " ".join(
            f"[{item.source_id}] {item.title}: {(item.content or item.excerpt)[:500]}"
            for item in evidence
        )
        or None
    )
    if not evidence and not warnings:
        warnings.append("No usable research evidence was returned.")
    return WebResearchResult(
        summary=summary,
        sources=evidence,
        status="available" if evidence else "unavailable",
        warnings=_dedupe(warnings),
    )


async def _web_search(
    plan: ResearchPlan, gateway: MCPToolGateway
) -> tuple[list[WebSourceResult], list[str]]:
    if plan.current_or_cross_check:
        calls = [
            _call_and_normalize(
                gateway,
                "tavily",
                "tavily-search",
                {"query": plan.query, "max_results": 5, "search_depth": "basic"},
                "tavily",
                "news",
            ),
            _call_and_normalize(
                gateway,
                "brave",
                "brave_news_search",
                {"query": plan.query, "count": 5, "safesearch": "moderate"},
                "brave",
                "news",
            ),
        ]
        results = await asyncio.gather(*calls, return_exceptions=True)
        evidence: list[WebSourceResult] = []
        warnings: list[str] = []
        for provider, result in zip(("Tavily", "Brave"), results, strict=True):
            if isinstance(result, BaseException):
                warnings.append(f"{provider} search was unavailable.")
            else:
                evidence.extend(result)
        return evidence, warnings

    try:
        primary = await _call_and_normalize(
            gateway,
            "tavily",
            "tavily-search",
            {"query": plan.query, "max_results": 5, "search_depth": "basic"},
            "tavily",
            "web",
        )
        if primary:
            return primary, []
    except MCPError:
        pass
    trace = current_latency_trace()
    if trace is not None:
        trace.increment("mcp_fallback_count")
    try:
        fallback = await _call_and_normalize(
            gateway,
            "brave",
            "brave_web_search",
            {"query": plan.query, "count": 5, "safesearch": "moderate"},
            "brave",
            "web",
        )
        return fallback, ["Tavily was unavailable; Brave fallback was used."]
    except MCPError:
        return [], ["Tavily and Brave search were unavailable."]


async def _academic_search(
    plan: ResearchPlan, gateway: MCPToolGateway
) -> tuple[list[WebSourceResult], list[str]]:
    if plan.doi:
        calls = [
            _call_and_normalize(
                gateway,
                "academic",
                "lookup_doi",
                {"doi": plan.doi},
                "academic",
                "academic",
            )
        ]
    else:
        calls = [
            _call_and_normalize(
                gateway,
                "academic",
                tool,
                {"query": plan.query, "limit": 5},
                "academic",
                "academic",
            )
            for tool in ("search_arxiv", "search_openalex")
        ]
    results = await asyncio.gather(*calls, return_exceptions=True)
    evidence: list[WebSourceResult] = []
    failed = 0
    for result in results:
        if isinstance(result, BaseException):
            failed += 1
        else:
            evidence.extend(result)
    warnings = (
        ["Academic search was partially unavailable."]
        if failed and evidence
        else ["Academic search was unavailable; general web fallback was used."]
        if failed
        else []
    )
    return evidence, warnings


async def _fetch_pages(
    evidence: list[WebSourceResult],
    urls: list[str],
    gateway: MCPToolGateway,
    settings: Settings,
) -> tuple[list[WebSourceResult], list[str]]:
    started_at = perf_counter()
    calls = [
        gateway.call(
            "fetch",
            "fetch",
            {
                "url": url,
                "max_characters": settings.mcp_fetch_max_content_characters,
            },
        )
        for url in urls
    ]
    results = await asyncio.gather(*calls, return_exceptions=True)
    warnings: list[str] = []
    enriched = evidence
    for url, result in zip(urls, results, strict=True):
        if isinstance(result, BaseException):
            warnings.append(
                "A selected page could not be read; its snippet was retained."
            )
            continue
        content = _content_from_fetch(result)
        if content:
            enriched = attach_page_content(enriched, url, content)
    trace = current_latency_trace()
    if trace is not None:
        trace.record("mcp_fetch", (perf_counter() - started_at) * 1000)
    return enriched, warnings


async def _call_and_normalize(
    gateway: MCPToolGateway,
    server: str,
    tool: str,
    arguments: dict[str, object],
    provider: str,
    source_type: str,
) -> list[WebSourceResult]:
    payload = await gateway.call(server, tool, arguments)
    return normalize_evidence(
        payload,
        provider=provider,
        source_type=source_type,  # type: ignore[arg-type]
    )


def _content_from_fetch(payload: dict[str, object] | list[object]) -> str:
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    return content.strip() if isinstance(content, str) else ""


def _activity(callback: ActivityCallback | None, stage: str, message: str) -> None:
    if callback is not None:
        callback(stage, message)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
