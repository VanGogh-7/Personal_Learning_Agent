from dataclasses import dataclass

from app.agents.local_library import LocalLibraryAgentResult
from app.agents.router import AgentRoute
from app.agents.web_research import WebResearchResult, WebSourceResult
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
    """Combine fixed local and web agent outputs into one stable MVP answer."""
    local_summary = local_result.summary if local_result is not None else None
    web_summary = web_result.summary if web_result is not None else None
    warnings = list(web_result.warnings) if web_result is not None else []
    errors = list(web_result.errors) if web_result is not None else []
    web_unavailable = web_result is not None and web_result.status == "unavailable"
    has_local_evidence = (
        local_result is not None and local_result.evidence_quality != "none"
    )
    local_answer = (
        append_local_source_ids(local_summary, local_result.citations)
        if local_summary and local_result is not None and has_local_evidence
        else local_summary
    )

    if route == "local_only":
        answer = build_local_only_answer(local_result, local_answer)
    elif route == "web_only":
        answer = build_web_only_answer(web_result, web_summary, web_unavailable)
    else:
        if web_unavailable and has_local_evidence:
            warnings.append(
                "Web research was skipped because no web provider is configured; answer uses local Library evidence only."
            )
        answer = build_both_answer(
            local_result=local_result,
            local_answer=local_answer,
            web_result=web_result,
            web_summary=web_summary,
            web_unavailable=web_unavailable,
        )

    if llm_provider is not None:
        answer = llm_provider.generate(
            build_synthesis_prompt(
                question=question,
                route=route,
                deterministic_answer=answer,
                local_summary=local_summary,
                web_summary=web_summary,
                web_sources=web_result.sources if web_result is not None else [],
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
    web_sources: list[WebSourceResult] | None = None,
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
        "When using web evidence, cite claims with the provided [W#] IDs.",
        "Do not invent source IDs or alternate source labels.",
        "Keep local Library citations and web source IDs visually separate.",
        "For route=both, use concise sections: From your library, External context, Synthesis, Sources.",
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

    if web_sources:
        lines.extend(["", "Web Research sources:"])
        for source in web_sources:
            label = f"[{source.source_id}] {source.title}; {source.url}"
            if source.published_date:
                label += f"; published {source.published_date}"
            lines.append(label)
            lines.append("Text:")
            lines.append(source.excerpt.strip())

    lines.extend(["", DETERMINISTIC_ANSWER_MARKER, deterministic_answer])
    return "\n".join(lines)


def build_local_only_answer(
    local_result: LocalLibraryAgentResult | None,
    local_answer: str | None,
) -> str:
    if local_result is None or local_result.evidence_quality == "none":
        return "\n\n".join(
            [
                "From your library",
                "I could not find relevant information in the selected local Library evidence.",
                "Sources",
                "No local citations were available.",
            ]
        )

    lines = [
        "From your library",
        local_answer or "I found local Library evidence, but no summary was produced.",
    ]
    if local_result.evidence_quality == "weak":
        lines.append(
            "The retrieved local evidence looks weak, so treat this as limited book evidence."
        )
    lines.extend(["Sources", format_local_source_list(local_result.citations)])
    return "\n\n".join(lines)


def build_web_only_answer(
    web_result: WebResearchResult | None,
    web_summary: str | None,
    web_unavailable: bool,
) -> str:
    if web_result is None or web_unavailable:
        return "\n\n".join(
            [
                "External context",
                (
                    "Web research is unavailable or skipped, so I cannot answer this "
                    "current or external question from web evidence."
                ),
                "Sources",
                "No web sources were available.",
            ]
        )

    return "\n\n".join(
        [
            "External context",
            web_summary or "Web research completed, but no usable summary was produced.",
            "Sources",
            format_web_source_list(web_result.sources),
        ]
    )


def build_both_answer(
    *,
    local_result: LocalLibraryAgentResult | None,
    local_answer: str | None,
    web_result: WebResearchResult | None,
    web_summary: str | None,
    web_unavailable: bool,
) -> str:
    has_local_evidence = (
        local_result is not None and local_result.evidence_quality != "none"
    )
    has_web_evidence = (
        web_result is not None
        and not web_unavailable
        and bool(web_summary or web_result.sources)
    )

    if has_local_evidence:
        local_section = local_answer or "Local Library evidence was found, but no summary was produced."
        if local_result.evidence_quality == "weak":
            local_section += (
                " The retrieved local evidence looks weak, so treat this as limited book evidence."
            )
    else:
        local_section = "I could not find supported local Library evidence for this question."

    if has_web_evidence:
        web_section = web_summary or "Web research returned sources, but no summary was produced."
    elif web_unavailable:
        web_section = "Web research is unavailable or skipped for this request."
    else:
        web_section = "No usable web research result was available."

    synthesis_section = build_combined_synthesis_sentence(
        has_local_evidence=has_local_evidence,
        has_web_evidence=has_web_evidence,
        web_unavailable=web_unavailable,
    )

    local_sources = (
        format_local_source_list(local_result.citations)
        if local_result is not None
        else "none"
    )
    web_sources = (
        format_web_source_list(web_result.sources)
        if web_result is not None and not web_unavailable
        else "none"
    )

    return "\n\n".join(
        [
            "From your library",
            local_section,
            "External context",
            web_section,
            "Synthesis",
            synthesis_section,
            "Sources",
            f"Library: {local_sources}\nWeb: {web_sources}",
        ]
    )


def build_combined_synthesis_sentence(
    *,
    has_local_evidence: bool,
    has_web_evidence: bool,
    web_unavailable: bool,
) -> str:
    if has_local_evidence and has_web_evidence:
        return (
            "Use the library evidence as the book-grounded answer and the web result "
            "only as external context."
        )
    if has_local_evidence and web_unavailable:
        return "The answer is based on local Library evidence only because web research is unavailable."
    if has_local_evidence:
        return "The answer is based on local Library evidence; no usable web context was available."
    if has_web_evidence:
        return "No supported local Library evidence was found, so the answer relies on external web context."
    return "Neither supported local Library evidence nor usable web context was available."


def format_local_source_list(local_citations: list[ChunkCitationResult]) -> str:
    if not local_citations:
        return "none"
    return ", ".join(f"[{citation.citation_id}]" for citation in local_citations)


def format_web_source_list(web_sources: list[WebSourceResult]) -> str:
    if not web_sources:
        return "none"
    return ", ".join(f"[{source.source_id}]" for source in web_sources)


def append_local_source_ids(
    answer: str,
    local_citations: list[ChunkCitationResult],
) -> str:
    if not local_citations:
        return answer
    source_ids = [citation.citation_id for citation in local_citations]
    if any(f"[{source_id}]" in answer for source_id in source_ids):
        return answer
    formatted_ids = ", ".join(f"[{source_id}]" for source_id in source_ids)
    return f"{answer} Local book sources: {formatted_ids}."


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in seen:
            deduped.append(stripped)
            seen.add(stripped)
    return deduped
