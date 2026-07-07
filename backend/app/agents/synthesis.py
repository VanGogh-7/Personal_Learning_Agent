from dataclasses import dataclass

from app.agents.local_library import LocalLibraryAgentResult
from app.agents.router import AgentRoute
from app.agents.web_research import WebResearchResult


@dataclass(frozen=True)
class AgentSynthesisResult:
    answer: str
    local_summary: str | None
    web_summary: str | None


def synthesize_agent_answer(
    *,
    question: str,
    route: AgentRoute,
    local_result: LocalLibraryAgentResult | None = None,
    web_result: WebResearchResult | None = None,
) -> AgentSynthesisResult:
    """Combine fixed local and web agent outputs into one deterministic answer."""
    local_summary = local_result.summary if local_result is not None else None
    web_summary = web_result.summary if web_result is not None else None

    if route == "local_only":
        answer = local_summary or "I could not find relevant information in the local Library."
    elif route == "web_only":
        answer = web_summary or "No web research result is available."
    else:
        parts: list[str] = []
        if local_summary:
            parts.append(local_summary)
        if web_summary:
            parts.append(f"Web research: {web_summary}")
        answer = " ".join(parts) if parts else (
            "I could not find local or web evidence for this question."
        )

    return AgentSynthesisResult(
        answer=answer,
        local_summary=local_summary,
        web_summary=web_summary,
    )

