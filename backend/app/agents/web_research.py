from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.core.config import get_settings

WEB_EXCERPT_LENGTH = 240

WebResearchStatus = Literal["available", "unavailable", "skipped"]


@dataclass(frozen=True)
class WebSourceResult:
    source_id: str
    title: str
    url: str
    excerpt: str
    provider: str = "deterministic"


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
            "Deterministic web research summary. "
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

    Stage 46 intentionally ships no live network provider. The
    deterministic provider is opt-in for tests and local demos.
    """
    provider_name = get_settings().web_research_provider.strip().lower()
    if provider_name in {"", "none", "unavailable", "disabled"}:
        return UnavailableWebResearchProvider()
    if provider_name in {"deterministic", "mock"}:
        return DeterministicWebResearchProvider()
    return UnavailableWebResearchProvider()


def run_web_research_agent(
    question: str,
    provider: WebResearchProvider | None = None,
) -> WebResearchResult:
    """Run the fixed Web Research Agent boundary without direct network coupling."""
    resolved_provider = provider or get_web_research_provider()
    return resolved_provider.research(question)
