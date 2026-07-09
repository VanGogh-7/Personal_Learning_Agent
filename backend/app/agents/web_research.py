import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

WEB_EXCERPT_LENGTH = 240
WEB_SUMMARY_SNIPPET_LENGTH = 220

WebResearchStatus = Literal["available", "unavailable", "skipped"]
HttpPostJson = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]


@dataclass(frozen=True)
class WebSourceResult:
    source_id: str
    title: str
    url: str
    excerpt: str
    provider: str = "deterministic"
    published_date: str | None = None


@dataclass(frozen=True)
class WebResearchResult:
    summary: str | None
    sources: list[WebSourceResult]
    status: WebResearchStatus = "available"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class WebResearchProvider(Protocol):
    provider_name: str

    def research(self, question: str) -> WebResearchResult:
        """Return structured web research without leaking provider details."""


class UnavailableWebResearchProvider:
    """Default provider boundary when no real web research is configured."""

    provider_name = "unavailable"

    def research(self, question: str) -> WebResearchResult:
        return WebResearchResult(
            summary=None,
            sources=[],
            status="unavailable",
            warnings=[
                "Web research is unavailable because no web provider is configured."
            ],
        )


class TavilyWebResearchProvider:
    """Minimal Tavily Search API provider.

    It intentionally uses one search request and maps Tavily's structured
    result objects into the app's stable WebSourceResult shape.
    """

    provider_name = "tavily"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.tavily.com/search",
        search_depth: str = "basic",
        max_results: int = 5,
        timeout_seconds: float = 10.0,
        http_post_json: HttpPostJson | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.strip() or "https://api.tavily.com/search"
        self.search_depth = search_depth.strip() or "basic"
        self.max_results = max(1, min(max_results, 10))
        self.timeout_seconds = timeout_seconds
        self.http_post_json = http_post_json or post_json

    def research(self, question: str) -> WebResearchResult:
        if not self.api_key:
            return WebResearchResult(
                summary=None,
                sources=[],
                status="unavailable",
                warnings=[
                    "Tavily web research is unavailable because TAVILY_API_KEY is not configured."
                ],
            )

        payload = {
            "query": question.strip(),
            "search_depth": self.search_depth,
            "max_results": self.max_results,
            "topic": "general",
            "include_answer": True,
            "include_raw_content": False,
            "include_images": False,
            "include_image_descriptions": False,
            "include_favicon": False,
            "safe_search": True,
        }
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = self.http_post_json(
                self.base_url,
                payload,
                headers,
                self.timeout_seconds,
            )
        except HTTPError as exc:
            return tavily_failure_result(f"status {exc.code}")
        except (URLError, TimeoutError, OSError):
            return tavily_failure_result("network error")
        except ValueError:
            return tavily_failure_result("invalid JSON response")

        sources = tavily_sources_from_response(response)
        summary = tavily_summary_from_response(response, sources)
        if not sources and not summary:
            return WebResearchResult(
                summary=None,
                sources=[],
                status="unavailable",
                warnings=["Tavily web research returned no usable results."],
            )

        return WebResearchResult(
            summary=summary,
            sources=sources,
            status="available",
        )


class DeterministicWebResearchProvider:
    """Mock web research boundary for deterministic tests and local demos."""

    provider_name = "deterministic"

    def research(self, question: str) -> WebResearchResult:
        normalized_question = " ".join(question.strip().split())
        excerpt_question = normalized_question[:WEB_EXCERPT_LENGTH]
        source = WebSourceResult(
            source_id="W1",
            title="Deterministic web research placeholder",
            url="mock://web-research/deterministic",
            excerpt=f"Mock web research result for: {excerpt_question}",
            provider=self.provider_name,
        )
        summary = (
            "Deterministic web research summary [W1]. "
            "No live network request was made. "
            f"Question considered: {excerpt_question}"
        )
        return WebResearchResult(
            summary=summary,
            sources=[source],
            status="available",
        )


def get_web_research_provider() -> WebResearchProvider:
    """Resolve the configured Web Research provider.

    Stage 47 keeps live web search opt-in. The deterministic provider
    remains available for tests and local demos.
    """
    provider_name = get_settings().web_research_provider.strip().lower()
    if provider_name in {"", "none", "unavailable", "disabled"}:
        return UnavailableWebResearchProvider()
    if provider_name in {"deterministic", "mock"}:
        return DeterministicWebResearchProvider()
    if provider_name == "tavily":
        settings = get_settings()
        return TavilyWebResearchProvider(
            api_key=settings.tavily_api_key,
            base_url=settings.tavily_base_url,
            search_depth=settings.tavily_search_depth,
            max_results=settings.tavily_max_results,
        )
    return UnavailableWebResearchProvider()


def run_web_research_agent(
    question: str,
    provider: WebResearchProvider | None = None,
) -> WebResearchResult:
    """Run the fixed Web Research Agent boundary without direct network coupling."""
    resolved_provider = provider or get_web_research_provider()
    return resolved_provider.research(question)


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object response")
    return parsed


def tavily_failure_result(reason: str) -> WebResearchResult:
    return WebResearchResult(
        summary=None,
        sources=[],
        status="unavailable",
        warnings=[f"Tavily web research failed ({reason})."],
    )


def tavily_sources_from_response(response: dict[str, Any]) -> list[WebSourceResult]:
    raw_results = response.get("results", [])
    if not isinstance(raw_results, list):
        return []

    sources: list[WebSourceResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = string_or_empty(item.get("title")) or "Untitled web result"
        url = string_or_empty(item.get("url"))
        excerpt = string_or_empty(item.get("content") or item.get("snippet"))
        if not url or not excerpt:
            continue
        sources.append(
            WebSourceResult(
                source_id=f"W{len(sources) + 1}",
                title=title,
                url=url,
                excerpt=excerpt[:WEB_EXCERPT_LENGTH],
                provider="tavily",
                published_date=extract_published_date(item),
            )
        )
    return sources


def tavily_summary_from_response(
    response: dict[str, Any],
    sources: list[WebSourceResult],
) -> str | None:
    answer = string_or_empty(response.get("answer"))
    if answer:
        source_ids = ", ".join(source.source_id for source in sources)
        return f"{answer.strip()} ({source_ids})" if source_ids else answer.strip()
    if not sources:
        return None

    summaries = [
        f"[{source.source_id}] {source.title}: {source.excerpt[:WEB_SUMMARY_SNIPPET_LENGTH]}"
        for source in sources
    ]
    return " ".join(summaries)


def extract_published_date(item: dict[str, Any]) -> str | None:
    for key in ("published_date", "publishedDate", "date"):
        value = string_or_empty(item.get(key))
        if value:
            return value
    return None


def string_or_empty(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
