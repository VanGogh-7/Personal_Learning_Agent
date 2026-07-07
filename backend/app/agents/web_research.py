from dataclasses import dataclass


WEB_EXCERPT_LENGTH = 240


@dataclass(frozen=True)
class WebSourceResult:
    source_id: str
    title: str
    url: str
    excerpt: str
    provider: str = "deterministic"


@dataclass(frozen=True)
class WebResearchResult:
    summary: str
    sources: list[WebSourceResult]


class DeterministicWebResearchProvider:
    """Mock web research boundary used by default for local runs and tests."""

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
        return WebResearchResult(summary=summary, sources=[source])


def run_web_research_agent(
    question: str,
    provider: DeterministicWebResearchProvider | None = None,
) -> WebResearchResult:
    """Run the fixed Web Research Agent boundary.

    The MVP ships only a deterministic provider. Any real provider should
    be introduced later as an explicit opt-in configuration path.
    """
    resolved_provider = provider or DeterministicWebResearchProvider()
    return resolved_provider.research(question)

