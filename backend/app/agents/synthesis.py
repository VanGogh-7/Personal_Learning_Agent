from dataclasses import dataclass

from app.agents.local_library import LocalLibraryAgentResult
from app.agents.router import AgentRoute
from app.agents.web_research import WebResearchResult
from app.llm.providers import DETERMINISTIC_ANSWER_MARKER, LLMProvider
from app.rag.citations import ChunkCitationResult, format_citation_source


@dataclass(frozen=True)
class AgentSynthesisResult:
    answer: str
    local_summary: str | None
    web_summary: str | None
    warnings: list[str]
    errors: list[str]


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
    warnings = list(web_result.warnings) if web_result is not None else []
    errors = list(web_result.errors) if web_result is not None else []
    web_unavailable = web_result is not None and web_result.status == "unavailable"
    has_local_evidence = (
        local_result is not None and local_result.evidence_quality != "none"
    )

    if route == "local_only":
        answer = local_summary or "I could not find relevant information in the local Library."
    elif route == "web_only":
        if web_unavailable:
            answer = (
                "Web research is unavailable because no web provider is configured. "
                "I cannot answer this current or external question from web evidence."
            )
        else:
            answer = web_summary or "No web research result is available."
    else:
        parts: list[str] = []
        if local_summary and has_local_evidence:
            parts.append(local_summary)
        if web_summary and not web_unavailable:
            parts.append(f"Web research: {web_summary}")
        if web_unavailable and has_local_evidence:
            warnings.append(
                "Web research was skipped because no web provider is configured; answer uses local Library evidence only."
            )
        answer = " ".join(parts) if parts else (
            "I could not find supported local evidence, and web research is unavailable."
            if web_unavailable
            else "I could not find local or web evidence for this question."
        )

    if llm_provider is not None:
        answer = llm_provider.generate(
            build_synthesis_prompt(
                question=question,
                route=route,
                deterministic_answer=answer,
                local_summary=local_summary,
                web_summary=web_summary,
                local_citations=local_result.citations
                if local_result is not None
                else [],
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
        warnings=dedupe_strings(warnings),
        errors=dedupe_strings(errors),
    )


def build_synthesis_prompt(
    *,
    question: str,
    route: AgentRoute,
    deterministic_answer: str,
    local_summary: str | None,
    web_summary: str | None,
    local_citations: list[ChunkCitationResult] | None = None,
    local_citation_count: int,
    web_source_count: int,
) -> str:
    """Build a bounded prompt for final answer synthesis."""
    lines = [
        "Synthesize a final learning answer from the fixed agent outputs.",
        "Use only the provided local and web summaries.",
        "If evidence is missing, say so clearly.",
        "When using local Library evidence, cite claims with the provided [S#] IDs.",
        "Do not invent source IDs or alternate source labels.",
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

    if local_citations:
        lines.extend(["", "Local Library sources:"])
        for citation in local_citations:
            lines.append(format_citation_source(citation))
            lines.append("Text:")
            lines.append(citation.content.strip())

    if web_summary:
        lines.extend(["", "Web Research Agent summary:", web_summary.strip()])

    lines.extend(["", DETERMINISTIC_ANSWER_MARKER, deterministic_answer])
    return "\n".join(lines)


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in seen:
            deduped.append(stripped)
            seen.add(stripped)
    return deduped
