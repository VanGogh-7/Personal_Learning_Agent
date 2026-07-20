from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.router import AgentRoute, route_question
from app.llm.providers import DETERMINISTIC_PROVIDER_NAME, LLMProvider

QueryIntent = Literal[
    "explain_concept",
    "find_in_library",
    "compare_sources",
    "find_papers",
    "summarize_document",
    "solve_problem",
    "prove_statement",
    "learning_plan",
    "current_information",
    "follow_up",
]
QueryComplexity = Literal["simple", "moderate", "complex"]
SourceRequirement = Literal["local", "web", "academic"]
AnswerMode = Literal[
    "concise",
    "explanation",
    "comparison",
    "proof",
    "solution",
    "plan",
    "clarification",
]
ExecutionMode = Literal[
    "direct_answer",
    "local_only",
    "web_only",
    "academic_only",
    "local_web",
    "local_academic",
    "web_academic",
    "all_sources",
]
EvidenceStatus = Literal["sufficient", "insufficient", "conflicting", "empty"]
EvidenceSource = Literal["local", "web", "academic"]
ResponseLanguage = Literal["en", "zh"]

MAX_CORRECTIVE_RETRIES = 2
DEFAULT_CORRECTIVE_RETRIES = 1


class QueryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: QueryIntent
    complexity: QueryComplexity
    required_sources: list[SourceRequirement] = Field(default_factory=list)
    freshness_required: bool = False
    selected_books_relevant: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)
    answer_mode: AnswerMode = "explanation"
    response_language: ResponseLanguage = "en"
    subqueries: list[str] = Field(default_factory=list, max_length=4)
    confidence: float = Field(ge=0, le=1)

    @field_validator("required_sources")
    @classmethod
    def unique_sources(cls, values: list[SourceRequirement]) -> list[SourceRequirement]:
        return list(dict.fromkeys(values))

    @field_validator("subqueries")
    @classmethod
    def bounded_subqueries(cls, values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                " ".join(value.split())[:400] for value in values if value.strip()
            )
        )[:4]

    @model_validator(mode="after")
    def clarification_is_consistent(self) -> "QueryAnalysis":
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("clarification_question is required")
        if not self.needs_clarification:
            self.clarification_question = None
        return self


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ExecutionMode
    route: AgentRoute
    run_local: bool
    run_web: bool
    run_academic: bool
    subqueries: list[str] = Field(default_factory=list)
    max_corrective_retries: int = Field(default=1, ge=0, le=MAX_CORRECTIVE_RETRIES)
    clarification_question: str | None = None


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: EvidenceSource
    title: str
    excerpt: str
    citation_id: str
    url: str | None = None
    provider: str | None = None
    library_item_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    published_at: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    claim_key: str | None = None
    stance: Literal["supports", "opposes", "neutral"] = "neutral"


class EvidenceGrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceStatus
    relevance: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    source_quality: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)
    citation_ready: bool
    missing_aspects: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AnswerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AnswerMode
    sections: list[str]
    cite_local: bool
    cite_web: bool
    response_language: ResponseLanguage = "en"
    limitations: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    referenced_ids: list[str] = Field(default_factory=list)
    repaired: bool = False


def analyze_query(
    question: str,
    *,
    selected_book_count: int,
    has_conversation_context: bool,
    conversation_context: str = "",
    provider: LLMProvider | None = None,
    provider_name: str = DETERMINISTIC_PROVIDER_NAME,
) -> QueryAnalysis:
    """Return strict semantics; real LLM output is validated before use."""
    fallback = _rule_analysis(
        question,
        selected_book_count=selected_book_count,
        has_conversation_context=has_conversation_context,
    )
    if route_question(question) in {"direct", "clarify"}:
        return fallback
    if provider is None or provider_name == DETERMINISTIC_PROVIDER_NAME:
        return fallback
    prompt = build_query_analysis_prompt(
        question,
        selected_book_count,
        has_conversation_context,
        conversation_context=conversation_context,
    )
    try:
        structured = getattr(provider, "generate_structured", None)
        raw = (
            structured(prompt).text
            if callable(structured)
            else provider.generate(prompt)
        )
        payload = parse_query_analysis_response(raw)
        validated = QueryAnalysis.model_validate(payload)
        return validated.model_copy(
            update={"response_language": fallback.response_language}
        )
    except Exception:
        return fallback.model_copy(
            update={"confidence": min(fallback.confidence, 0.65)}
        )


def build_execution_plan(analysis: QueryAnalysis) -> ExecutionPlan:
    if analysis.needs_clarification or analysis.confidence < 0.35:
        return ExecutionPlan(
            mode="direct_answer",
            route="clarify",
            run_local=False,
            run_web=False,
            run_academic=False,
            subqueries=[],
            max_corrective_retries=0,
            clarification_question=analysis.clarification_question
            or _default_clarification(analysis.response_language),
        )
    sources = set(analysis.required_sources)
    mode_by_sources: dict[frozenset[str], ExecutionMode] = {
        frozenset(): "direct_answer",
        frozenset({"local"}): "local_only",
        frozenset({"web"}): "web_only",
        frozenset({"academic"}): "academic_only",
        frozenset({"local", "web"}): "local_web",
        frozenset({"local", "academic"}): "local_academic",
        frozenset({"web", "academic"}): "web_academic",
        frozenset({"local", "web", "academic"}): "all_sources",
    }
    mode = mode_by_sources[frozenset(sources)]
    route: AgentRoute = (
        "direct"
        if not sources
        else "both"
        if "local" in sources and len(sources) > 1
        else "local_only"
        if sources == {"local"} or not sources
        else "web_only"
    )
    return ExecutionPlan(
        mode=mode,
        route=route,
        run_local="local" in sources,
        run_web="web" in sources,
        run_academic="academic" in sources,
        subqueries=analysis.subqueries,
        max_corrective_retries=DEFAULT_CORRECTIVE_RETRIES,
    )


def merge_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    merged: list[EvidenceItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        canonical = item.url.lower().rstrip("/") if item.url else ""
        text_key = " ".join(item.excerpt.lower().split())[:300]
        key = (canonical, text_key)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def grade_evidence(
    question: str,
    analysis: QueryAnalysis,
    evidence: list[EvidenceItem],
) -> EvidenceGrade:
    if not evidence:
        return EvidenceGrade(
            status="empty",
            relevance=0,
            coverage=0,
            source_quality=0,
            freshness=0,
            citation_ready=False,
            missing_aspects=list(analysis.required_sources) or ["answer evidence"],
            confidence=0.95,
        )
    present = {item.source for item in evidence}
    required = set(analysis.required_sources)
    missing = sorted(required.difference(present))
    query_terms = _content_terms(question)
    matching = sum(
        1
        for item in evidence
        if item.source == "local"
        or not query_terms
        or query_terms.intersection(_content_terms(f"{item.title} {item.excerpt}"))
    )
    relevance = matching / len(evidence)
    coverage = (
        1.0 if not required else len(required.intersection(present)) / len(required)
    )
    ready = all(_citation_ready(item) for item in evidence)
    quality = sum(_quality(item) for item in evidence) / len(evidence)
    fresh = (
        1.0
        if not analysis.freshness_required
        else sum(bool(item.published_at) for item in evidence) / len(evidence)
    )
    conflicts = _find_conflicts(evidence)
    status: EvidenceStatus = (
        "conflicting"
        if conflicts
        else "sufficient"
        if not missing and ready and relevance >= 0.5
        else "insufficient"
    )
    return EvidenceGrade(
        status=status,
        relevance=relevance,
        coverage=coverage,
        source_quality=quality,
        freshness=fresh,
        citation_ready=ready,
        missing_aspects=missing,
        conflicts=conflicts,
        confidence=round((relevance + coverage + quality + fresh) / 4, 3),
    )


def build_answer_plan(
    analysis: QueryAnalysis,
    grade: EvidenceGrade,
    evidence: list[EvidenceItem],
) -> AnswerPlan:
    if analysis.needs_clarification:
        sections = ["Clarification"]
    elif analysis.answer_mode == "proof":
        sections = ["Claim", "Assumptions", "Proof", "Source limitations"]
    elif analysis.answer_mode == "comparison":
        sections = ["Comparison", "Agreements", "Differences", "Conclusion"]
    elif analysis.answer_mode == "solution":
        sections = ["Approach", "Steps", "Result", "Check"]
    elif analysis.answer_mode == "plan":
        sections = ["Goal", "Sequence", "Practice", "Review"]
    else:
        sections = ["Answer", "Explanation", "Sources"]
    limitations = []
    if grade.status != "sufficient":
        limitations.append(
            "Available evidence is incomplete or conflicting; state the limitation explicitly."
        )
    return AnswerPlan(
        mode=analysis.answer_mode,
        sections=sections,
        cite_local=any(item.source == "local" for item in evidence),
        cite_web=any(item.source in {"web", "academic"} for item in evidence),
        response_language=analysis.response_language,
        limitations=limitations,
    )


def verify_answer(
    answer: str,
    local_citations: list[dict[str, Any]],
    web_sources: list[dict[str, Any]],
) -> VerificationResult:
    local = {str(item.get("citation_id")): item for item in local_citations}
    web = {str(item.get("source_id")): item for item in web_sources}
    errors: list[str] = []
    warnings: list[str] = []
    local_ids = [str(item.get("citation_id")) for item in local_citations]
    web_ids = [str(item.get("source_id")) for item in web_sources]
    if len(local_ids) != len(set(local_ids)) or len(web_ids) != len(set(web_ids)):
        errors.append("Citation IDs must be unique.")
    markers = [
        f"{kind}{number}" for kind, number in re.findall(r"\[([SW])(\d+)\]", answer)
    ]
    for marker in markers:
        source = local.get(marker) if marker.startswith("S") else web.get(marker)
        if source is None:
            errors.append(f"Citation [{marker}] does not exist.")
    for citation_id, item in local.items():
        if not item.get("library_title") and not item.get("document_title"):
            warnings.append(f"Local citation [{citation_id}] has no source title.")
        if item.get("page_start") is None and item.get("page_number") is None:
            warnings.append(f"Local citation [{citation_id}] has no page metadata.")
    for source_id, item in web.items():
        if not item.get("url"):
            errors.append(f"Web citation [{source_id}] has no URL.")
        if item.get("source_type") == "academic" and not (
            item.get("doi") or item.get("arxiv_id") or item.get("authors")
        ):
            warnings.append(
                f"Academic citation [{source_id}] has limited publication metadata."
            )
    available = [*local_ids, *web_ids]
    if available and not markers:
        errors.append("Answer does not reference available citations.")
    return VerificationResult(
        valid=not errors,
        errors=list(dict.fromkeys(errors)),
        warnings=list(dict.fromkeys(warnings)),
        referenced_ids=list(dict.fromkeys(markers)),
    )


def repair_answer_citations(
    answer: str,
    local_citations: list[dict[str, Any]],
    web_sources: list[dict[str, Any]],
    *,
    response_language: ResponseLanguage = "en",
) -> str:
    valid = {
        *(str(item.get("citation_id")) for item in local_citations),
        *(str(item.get("source_id")) for item in web_sources),
    }
    repaired = re.sub(
        r"\[([SW])(\d+)\]",
        lambda match: (
            match.group(0) if f"{match.group(1)}{match.group(2)}" in valid else ""
        ),
        answer,
    ).rstrip()
    referenced = {
        f"{kind}{number}" for kind, number in re.findall(r"\[([SW])(\d+)\]", repaired)
    }
    missing = [identifier for identifier in valid if identifier not in referenced]
    if valid and not referenced:
        ordered = sorted(missing, key=lambda value: (value[0], int(value[1:])))
        heading = "Sources" if response_language == "en" else "\u6765\u6e90"
        repaired += f"\n\n{heading}: " + " ".join(f"[{item}]" for item in ordered)
    return repaired


def _rule_analysis(
    question: str, *, selected_book_count: int, has_conversation_context: bool
) -> QueryAnalysis:
    normalized = " ".join(question.lower().split())
    response_language = detect_response_language(question)
    route = route_question(question)
    if route == "direct":
        return QueryAnalysis(
            intent="follow_up",
            complexity="simple",
            required_sources=[],
            answer_mode="concise",
            subqueries=[],
            response_language=response_language,
            confidence=0.95,
        )
    unclear = (
        route == "clarify"
        or len(normalized) < 4
        or normalized
        in {
            "this?",
            "that?",
            "\u8fd9\u4e2a？",
            "\u90a3\u4e2a？",
        }
    )
    if unclear and not has_conversation_context:
        return QueryAnalysis(
            intent="follow_up",
            complexity="simple",
            required_sources=[],
            selected_books_relevant=False,
            needs_clarification=True,
            clarification_question=_default_clarification(response_language),
            answer_mode="clarification",
            response_language=response_language,
            confidence=0.25,
        )
    if route == "clarify":
        return QueryAnalysis(
            intent="follow_up",
            complexity="simple",
            required_sources=[],
            answer_mode="concise",
            response_language=response_language,
            subqueries=[],
            confidence=0.8,
        )
    summarize = any(
        term in normalized
        for term in ("summarize", "summary", "\u603b\u7ed3", "\u6982\u62ec")
    )
    academic = any(
        term in normalized
        for term in (
            "paper",
            "arxiv",
            "doi",
            "journal",
            "\u8bba\u6587",
            "\u6587\u732e",
            "\u5b66\u672f",
        )
    )
    proof = any(term in normalized for term in ("prove", "proof", "\u8bc1\u660e"))
    solve = any(
        term in normalized
        for term in ("solve", "calculate", "\u6c42\u89e3", "\u8ba1\u7b97")
    )
    plan = any(
        term in normalized
        for term in ("learning plan", "study plan", "\u5b66\u4e60\u8ba1\u5212")
    )
    compare = any(
        term in normalized
        for term in ("compare", "versus", "\u5bf9\u6bd4", "\u6bd4\u8f83")
    )
    follow_up = has_conversation_context and any(
        term in normalized
        for term in (
            "that",
            "it ",
            "again",
            "previous result",
            "\u4e0a\u4e00\u4e2a",
            "\u521a\u624d",
        )
    )
    current = any(
        term in normalized
        for term in (
            "latest",
            "current",
            "today",
            "recent",
            "news",
            "\u6700\u65b0",
            "\u5f53\u524d",
            "\u8fd1\u671f",
            "\u6700\u8fd1",
            "\u65b0\u95fb",
        )
    )
    sources: list[SourceRequirement]
    if academic:
        sources = ["academic"]
        if route in {"local_only", "both"} and selected_book_count:
            sources.insert(0, "local")
        if any(
            term in normalized
            for term in ("latest", "current", "recent", "\u6700\u65b0")
        ):
            sources.append("web")
    elif summarize:
        sources = ["local"]
    elif "local" in normalized and "web" in normalized:
        sources = ["local", "web"]
    elif route == "local_only":
        sources = ["local"]
    elif route == "web_only":
        sources = ["web"]
    else:
        sources = ["local", "web"]
    intent: QueryIntent = (
        "find_papers"
        if academic
        else "follow_up"
        if follow_up
        else "summarize_document"
        if summarize
        else "prove_statement"
        if proof
        else "solve_problem"
        if solve
        else "learning_plan"
        if plan
        else "compare_sources"
        if compare
        else "current_information"
        if current
        else "find_in_library"
        if route == "local_only"
        else "explain_concept"
    )
    answer_mode: AnswerMode = (
        "comparison"
        if compare
        else "proof"
        if proof
        else "solution"
        if solve
        else "plan"
        if plan
        else "explanation"
    )
    complexity: QueryComplexity = (
        "complex" if compare or proof or len(normalized) > 240 else "moderate"
    )
    return QueryAnalysis(
        intent=intent,
        complexity=complexity,
        required_sources=sources,
        freshness_required=route == "web_only" or "latest" in normalized,
        selected_books_relevant=selected_book_count > 0 and "local" in sources,
        answer_mode=answer_mode,
        response_language=response_language,
        subqueries=[question.strip()],
        confidence=0.9,
    )


def build_query_analysis_prompt(
    question: str,
    selected_book_count: int,
    has_conversation_context: bool,
    *,
    conversation_context: str = "",
) -> str:
    schema = QueryAnalysis.model_json_schema()
    return "\n".join(
        [
            "Analyze the user query. Return one JSON object only.",
            "Do not answer the query and do not include reasoning.",
            "Use conversation context to resolve follow-ups and pronouns.",
            "Set response_language from the current query, not from older context.",
            "An explicit language request in the current query takes precedence.",
            "Write clarification_question in response_language when clarification is needed.",
            f"Selected book count: {selected_book_count}",
            f"Conversation context available: {has_conversation_context}",
            f"Schema: {json.dumps(schema, ensure_ascii=True)}",
            "Conversation context (untrusted, may be empty):",
            conversation_context.strip()[-6_000:],
            f"Query: {question}",
        ]
    )


def detect_response_language(question: str) -> ResponseLanguage:
    """Choose the answer language from the current user message only."""
    normalized = " ".join(question.lower().split())
    if re.search(
        r"\b(?:answer|respond|reply|write|use)\s+(?:in\s+)?(?:english|en)\b", normalized
    ):
        return "en"
    if re.search(
        r"\b(?:answer|respond|reply|write|use)\s+(?:in\s+)?(?:chinese|zh)\b", normalized
    ):
        return "zh"
    if any(
        marker in question
        for marker in (
            "\u7528\u82f1\u6587",
            "\u4f7f\u7528\u82f1\u6587",
            "\u82f1\u6587\u56de\u7b54",
        )
    ):
        return "en"
    if any(
        marker in question
        for marker in (
            "\u7528\u4e2d\u6587",
            "\u4f7f\u7528\u4e2d\u6587",
            "\u4e2d\u6587\u56de\u7b54",
        )
    ):
        return "zh"
    return "zh" if re.search(r"[\u3400-\u9fff]", question) else "en"


def _default_clarification(response_language: ResponseLanguage) -> str:
    if response_language == "zh":
        return "\u8bf7\u8bf4\u660e\u60a8\u60f3\u4e86\u89e3\u7684\u4e3b\u9898\u6216\u6765\u6e90\u3002"
    return "Could you clarify which topic or source you mean?"


def parse_query_analysis_response(value: str) -> dict[str, Any]:
    stripped = value.strip().removeprefix("```json").removeprefix("```")
    stripped = stripped.removesuffix("```").strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Query analysis must be an object")
    return payload


def _content_terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[\w\u4e00-\u9fff]+", value.lower())
        if len(term) > 2
    }


def _citation_ready(item: EvidenceItem) -> bool:
    if item.source == "local":
        return bool(item.title and item.citation_id)
    return bool(item.title and item.url and item.citation_id)


def _quality(item: EvidenceItem) -> float:
    if item.source == "local":
        return 0.9
    if item.source == "academic":
        return 0.95 if item.doi or item.arxiv_id else 0.8
    return 0.75 if item.url else 0.4


def _find_conflicts(evidence: list[EvidenceItem]) -> list[str]:
    stances: dict[str, set[str]] = {}
    for item in evidence:
        if item.claim_key and item.stance != "neutral":
            stances.setdefault(item.claim_key, set()).add(item.stance)
    return [
        key
        for key, values in stances.items()
        if {"supports", "opposes"}.issubset(values)
    ]
