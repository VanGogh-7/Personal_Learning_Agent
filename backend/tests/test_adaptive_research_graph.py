import json

import pytest
from pydantic import ValidationError

from app.graphs.adaptive import (
    EvidenceGrade,
    EvidenceItem,
    QueryAnalysis,
    analyze_query,
    build_answer_plan,
    build_execution_plan,
    grade_evidence,
    merge_evidence,
    repair_answer_citations,
    verify_answer,
)
from app.graphs.chat_rag_graph import corrective_route
from app.mcp.client import MCPError
from app.mcp.gateway import MCPToolGateway
from app.core.config import Settings


def analysis(**changes) -> QueryAnalysis:
    values = {
        "intent": "explain_concept",
        "complexity": "moderate",
        "required_sources": ["local"],
        "answer_mode": "explanation",
        "subqueries": ["Banach space definition"],
        "confidence": 0.9,
    }
    values.update(changes)
    return QueryAnalysis.model_validate(values)


def evidence(
    identifier: str,
    source: str = "local",
    **changes,
) -> EvidenceItem:
    values = {
        "evidence_id": identifier,
        "source": source,
        "title": "Functional Analysis",
        "excerpt": "A Banach space is a complete normed vector space.",
        "citation_id": "S1" if source == "local" else "W1",
        "url": None if source == "local" else "https://example.test/source",
    }
    values.update(changes)
    return EvidenceItem.model_validate(values)


def test_query_analysis_schema_is_strict_and_clarification_is_consistent() -> None:
    with pytest.raises(ValidationError):
        QueryAnalysis.model_validate(
            {
                **analysis().model_dump(),
                "unknown_internal_reasoning": "not allowed",
            }
        )
    with pytest.raises(ValidationError, match="clarification_question"):
        analysis(needs_clarification=True)


def test_query_analysis_uses_validated_llm_json_and_falls_back_safely() -> None:
    class Provider:
        def generate(self, prompt: str) -> str:
            return json.dumps(
                analysis(
                    intent="find_papers",
                    required_sources=["academic"],
                    answer_mode="comparison",
                ).model_dump()
            )

    result = analyze_query(
        "Find papers about Banach spaces",
        selected_book_count=0,
        has_conversation_context=False,
        provider=Provider(),  # type: ignore[arg-type]
        provider_name="deepseek",
    )
    assert result.intent == "find_papers"
    assert result.required_sources == ["academic"]

    class InvalidProvider:
        def generate(self, prompt: str) -> str:
            return "not-json"

    fallback = analyze_query(
        "Find an arXiv paper",
        selected_book_count=0,
        has_conversation_context=False,
        provider=InvalidProvider(),  # type: ignore[arg-type]
        provider_name="deepseek",
    )
    assert fallback.required_sources == ["academic"]
    assert fallback.confidence <= 0.65


@pytest.mark.parametrize(
    ("sources", "mode"),
    [
        ([], "direct_answer"),
        (["local"], "local_only"),
        (["web"], "web_only"),
        (["academic"], "academic_only"),
        (["local", "web"], "local_web"),
        (["local", "academic"], "local_academic"),
        (["web", "academic"], "web_academic"),
        (["local", "web", "academic"], "all_sources"),
    ],
)
def test_deterministic_planning_supports_only_fixed_modes(sources, mode) -> None:
    plan = build_execution_plan(analysis(required_sources=sources))
    assert plan.mode == mode
    assert plan.run_local is ("local" in sources)
    assert plan.run_web is ("web" in sources)
    assert plan.run_academic is ("academic" in sources)


def test_low_confidence_enters_clarification_without_research() -> None:
    plan = build_execution_plan(
        analysis(
            confidence=0.2,
            needs_clarification=True,
            clarification_question="Which theorem do you mean?",
            answer_mode="clarification",
        )
    )
    assert plan.mode == "direct_answer"
    assert not plan.run_local and not plan.run_web and not plan.run_academic


def test_evidence_merge_deduplicates_and_grades_all_states() -> None:
    first = evidence("one")
    duplicate = evidence("two")
    merged = merge_evidence([first, duplicate])
    assert merged == [first]

    sufficient = grade_evidence("Banach space", analysis(), merged)
    assert sufficient.status == "sufficient"

    insufficient = grade_evidence(
        "Banach space",
        analysis(required_sources=["local", "web"]),
        merged,
    )
    assert insufficient.status == "insufficient"
    assert insufficient.missing_aspects == ["web"]

    empty = grade_evidence("Banach space", analysis(), [])
    assert empty.status == "empty"

    conflicting_items = [
        evidence("yes", claim_key="claim", stance="supports"),
        evidence(
            "no",
            source="web",
            citation_id="W1",
            excerpt="A contrary result.",
            claim_key="claim",
            stance="opposes",
        ),
    ]
    conflicting = grade_evidence(
        "Banach space",
        analysis(required_sources=["local", "web"]),
        conflicting_items,
    )
    assert conflicting.status == "conflicting"
    assert conflicting.conflicts == ["claim"]


def test_corrective_route_is_bounded() -> None:
    plan = build_execution_plan(analysis(required_sources=["local"]))
    grade = EvidenceGrade(
        status="empty",
        relevance=0,
        coverage=0,
        source_quality=0,
        freshness=0,
        citation_ready=False,
        confidence=1,
    )
    state = {
        "execution_plan": plan.model_dump(),
        "evidence_grade": grade.model_dump(),
        "retrieval_retry_count": 0,
        "retrieved_chunks": [],
    }
    assert corrective_route(state) == "correct"  # type: ignore[arg-type]
    state["retrieval_retry_count"] = plan.max_corrective_retries
    assert corrective_route(state) == "answer"  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_shared_gateway_budget_survives_corrective_calls() -> None:
    class Manager:
        async def call_tool(self, server, tool, arguments):
            return {}

    gateway = MCPToolGateway(
        manager=Manager(),  # type: ignore[arg-type]
        settings=Settings(mcp_max_calls_per_request=1),
    )
    await gateway.call("fetch", "fetch", {"url": "https://example.test"})
    with pytest.raises(MCPError, match="budget was exhausted"):
        await gateway.call("fetch", "fetch", {"url": "https://example.org"})


def test_citation_verification_repairs_unknown_and_missing_markers_once() -> None:
    local = [
        {
            "citation_id": "S1",
            "document_title": "Book",
            "page_start": 2,
        }
    ]
    web = [
        {
            "source_id": "W1",
            "title": "Article",
            "url": "https://example.test/article",
            "source_type": "web",
        }
    ]
    invalid = verify_answer("Claim [S9].", local, web)
    assert invalid.valid is False
    repaired_text = repair_answer_citations("Claim [S9].", local, web)
    repaired = verify_answer(repaired_text, local, web)
    assert repaired.valid is True
    assert "[S1]" in repaired_text and "[W1]" in repaired_text


def test_answer_plan_reflects_mode_and_evidence_limitations() -> None:
    grade = EvidenceGrade(
        status="insufficient",
        relevance=0.8,
        coverage=0.5,
        source_quality=0.9,
        freshness=1,
        citation_ready=True,
        missing_aspects=["web"],
        confidence=0.8,
    )
    plan = build_answer_plan(analysis(answer_mode="proof"), grade, [evidence("one")])
    assert plan.sections[0] == "Claim"
    assert plan.cite_local is True
    assert plan.limitations
