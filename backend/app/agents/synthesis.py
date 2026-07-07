from dataclasses import dataclass

from app.agents.local_library import LocalLibraryAgentResult
from app.agents.router import AgentRoute
from app.agents.web_research import WebResearchResult
from app.llm.providers import DETERMINISTIC_ANSWER_MARKER, LLMProvider


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
    llm_provider: LLMProvider | None = None,
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

    if llm_provider is not None:
        answer = llm_provider.generate(
            build_synthesis_prompt(
                question=question,
                route=route,
                deterministic_answer=answer,
                local_summary=local_summary,
                web_summary=web_summary,
                local_citation_count=(
                    len(local_result.citations) if local_result is not None else 0
                ),
                web_source_count=(
                    len(web_result.sources) if web_result is not None else 0
                ),
            )
        )

    return AgentSynthesisResult(
        answer=answer,
        local_summary=local_summary,
        web_summary=web_summary,
    )


def build_synthesis_prompt(
    *,
    question: str,
    route: AgentRoute,
    deterministic_answer: str,
    local_summary: str | None,
    web_summary: str | None,
    local_citation_count: int,
    web_source_count: int,
) -> str:
    """Build a bounded prompt for final answer synthesis."""
    lines = [
        "Synthesize a final learning answer from the fixed agent outputs.",
        "Use only the provided local and web summaries.",
        "If evidence is missing, say so clearly.",
        "",
        "Question:",
        question.strip(),
        "",
        f"Route: {route}",
        f"Local citation count: {local_citation_count}",
        f"Web source count: {web_source_count}",
    ]

    if local_summary:
        lines.extend(["", "Local Library Agent summary:", local_summary.strip()])

    if web_summary:
        lines.extend(["", "Web Research Agent summary:", web_summary.strip()])

    lines.extend(["", DETERMINISTIC_ANSWER_MARKER, deterministic_answer])
    return "\n".join(lines)
