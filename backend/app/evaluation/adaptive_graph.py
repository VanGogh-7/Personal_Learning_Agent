from __future__ import annotations

import json
import random
import statistics
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.graphs.adaptive import (
    AnswerMode,
    EvidenceGrade,
    EvidenceItem,
    ExecutionMode,
    QueryAnalysis,
    QueryIntent,
    SourceRequirement,
    analyze_query,
    build_execution_plan,
    grade_evidence,
    repair_answer_citations,
    verify_answer,
)
from app.llm.providers import LLMProvider, LLMStructuredResult, TokenUsage
from app.reliability.reporting import MeasurementSeries

GraphVariant = Literal[
    "adaptive",
    "direct_answer",
    "local_only",
    "web_only",
    "academic_only",
    "single_source_adaptive",
    "multi_source_adaptive",
    "correction_disabled",
    "correction_retry_1",
    "correction_retry_2",
]
EvidenceExpectation = Literal[
    "not_applicable", "sufficient", "insufficient", "conflicting", "empty"
]
CitationExpectation = Literal["not_applicable", "valid", "repairable", "invalid"]


class AdaptiveEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1_000)
    selected_book_count: int = Field(default=0, ge=0, le=20)
    has_conversation_context: bool = False
    expected_intent: QueryIntent
    expected_sources: list[SourceRequirement] = Field(default_factory=list)
    expected_route: ExecutionMode
    clarification_required: bool = False
    expected_answer_mode: AnswerMode
    evidence_expectation: EvidenceExpectation = "not_applicable"
    citation_expectation: CitationExpectation = "not_applicable"
    evidence: list[EvidenceItem] = Field(default_factory=list)
    expected_missing_aspects: list[str] = Field(default_factory=list)
    citation_answer: str | None = None
    local_citations: list[dict[str, Any]] = Field(default_factory=list)
    web_sources: list[dict[str, Any]] = Field(default_factory=list)
    corrected_evidence: list[EvidenceItem] = Field(default_factory=list)
    correction_extra_latency_ms: float = Field(default=0, ge=0)
    correction_extra_llm_calls: int = Field(default=0, ge=0)
    correction_extra_mcp_calls: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_fixtures(self) -> "AdaptiveEvaluationCase":
        if self.evidence_expectation != "not_applicable" and not (
            self.evidence or self.evidence_expectation == "empty"
        ):
            raise ValueError("Evidence fixture is required for this expectation")
        if (
            self.citation_expectation != "not_applicable"
            and self.citation_answer is None
        ):
            raise ValueError("Citation answer fixture is required")
        return self


class SemanticSupportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported_claims: int = Field(ge=0)
    evaluated_claims: int = Field(ge=0)


class ExperimentalLLMEvidenceGrader:
    """Evaluation-only candidate; never wired into the production graph."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def grade(
        self,
        question: str,
        analysis: QueryAnalysis,
        evidence: list[EvidenceItem],
    ) -> EvidenceGrade:
        method = getattr(self.provider, "generate_structured", None)
        if not callable(method):
            return grade_evidence(question, analysis, evidence)
        prompt = json.dumps(
            {
                "task": "Grade evidence only; return the EvidenceGrade JSON schema.",
                "question": question,
                "required_sources": analysis.required_sources,
                "evidence": [
                    {
                        "source": item.source,
                        "title": item.title,
                        "excerpt": item.excerpt[:1_000],
                        "citation_id": item.citation_id,
                    }
                    for item in evidence
                ],
            },
            ensure_ascii=False,
        )
        try:
            return EvidenceGrade.model_validate_json(method(prompt).text)
        except Exception:
            return grade_evidence(question, analysis, evidence)


class ExperimentalSemanticVerifier:
    """Evaluation-only citation-support judge with deterministic failure fallback."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def verify(
        self,
        answer: str,
        local_citations: list[dict[str, Any]],
        web_sources: list[dict[str, Any]],
    ) -> SemanticSupportResult | None:
        method = getattr(self.provider, "generate_structured", None)
        if not callable(method):
            return None
        prompt = json.dumps(
            {
                "task": (
                    "Count cited answer claims supported by the supplied source metadata. "
                    "Return supported_claims and evaluated_claims only."
                ),
                "answer": answer[:4_000],
                "local_sources": local_citations,
                "web_sources": [
                    {
                        key: source.get(key)
                        for key in ("source_id", "title", "url", "excerpt", "content")
                    }
                    for source in web_sources
                ],
            },
            ensure_ascii=False,
        )
        try:
            return SemanticSupportResult.model_validate_json(method(prompt).text)
        except Exception:
            return None


@dataclass
class AnalysisObservation:
    analysis: QueryAnalysis
    latency_ms: float
    schema_valid: bool
    used_fallback: bool
    usage: TokenUsage | None
    error_type: str | None = None


class TrackingStructuredProvider:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.last_result: LLMStructuredResult | None = None
        self.last_schema_valid = False

    def generate_structured(self, prompt: str) -> LLMStructuredResult:
        method = getattr(self.provider, "generate_structured", None)
        if not callable(method):
            result = LLMStructuredResult(text=self.provider.generate(prompt))
        else:
            result = method(prompt)
        self.last_result = result
        try:
            QueryAnalysis.model_validate(json.loads(result.text))
            self.last_schema_valid = True
        except Exception:
            self.last_schema_valid = False
        return result

    def generate(self, prompt: str) -> str:
        return self.generate_structured(prompt).text


def load_dataset(path: Path) -> list[AdaptiveEvaluationCase]:
    cases: list[AdaptiveEvaluationCase] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            case = AdaptiveEvaluationCase.model_validate_json(line)
        except Exception as exc:
            raise ValueError(f"Invalid evaluation case at line {line_number}") from exc
        if case.case_id in seen:
            raise ValueError(f"Duplicate evaluation case: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    return cases


def observe_analysis(
    case: AdaptiveEvaluationCase,
    *,
    provider: LLMProvider | None,
    provider_name: str,
) -> AnalysisObservation:
    tracking = TrackingStructuredProvider(provider) if provider is not None else None
    started = perf_counter()
    try:
        result = analyze_query(
            case.question,
            selected_book_count=case.selected_book_count,
            has_conversation_context=case.has_conversation_context,
            provider=tracking,  # type: ignore[arg-type]
            provider_name=provider_name,
        )
        elapsed = (perf_counter() - started) * 1_000
        if tracking is None or provider_name == "deterministic":
            return AnalysisObservation(result, elapsed, True, False, None)
        return AnalysisObservation(
            result,
            elapsed,
            tracking.last_schema_valid,
            not tracking.last_schema_valid,
            tracking.last_result.usage if tracking.last_result else None,
        )
    except Exception as exc:
        fallback = analyze_query(
            case.question,
            selected_book_count=case.selected_book_count,
            has_conversation_context=case.has_conversation_context,
        )
        return AnalysisObservation(
            fallback,
            (perf_counter() - started) * 1_000,
            False,
            True,
            None,
            type(exc).__name__,
        )


@dataclass
class EvaluationAccumulator:
    case_runs: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    analysis_latency: MeasurementSeries = field(default_factory=MeasurementSeries)


def evaluate_dataset(
    cases: list[AdaptiveEvaluationCase],
    *,
    variant: GraphVariant,
    runs: int,
    seed: int,
    provider: LLMProvider | None = None,
    provider_name: str = "deterministic",
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
    grader_adapter: ExperimentalLLMEvidenceGrader | None = None,
    semantic_adapter: ExperimentalSemanticVerifier | None = None,
    grader_name: str = "deterministic",
    semantic_verifier_name: str = "structural",
) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be positive")
    random.Random(seed).shuffle(cases := list(cases))
    accumulator = EvaluationAccumulator()
    signatures: dict[str, list[str]] = {case.case_id: [] for case in cases}
    for case in cases:
        for run_index in range(runs):
            try:
                observation = observe_analysis(
                    case, provider=provider, provider_name=provider_name
                )
                accumulator.analysis_latency.add_success(observation.latency_ms)
                plan = build_execution_plan(observation.analysis)
                predicted_mode, predicted_sources = _variant_prediction(
                    variant, plan.mode, observation.analysis.required_sources
                )
                signature = json.dumps(
                    {
                        "intent": observation.analysis.intent,
                        "sources": predicted_sources,
                        "route": predicted_mode,
                        "clarification": observation.analysis.needs_clarification,
                        "answer_mode": observation.analysis.answer_mode,
                    },
                    sort_keys=True,
                )
                signatures[case.case_id].append(signature)
                row = {
                    "request_id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"pla-stage58:{seed}:{case.case_id}:{run_index}",
                        )
                    ),
                    "case_id": case.case_id,
                    "category": case.category,
                    "run": run_index + 1,
                    "route": predicted_mode,
                    "analysis_llm_call": provider_name != "deterministic",
                    "base_mcp_calls": int("web" in predicted_sources)
                    + 2 * int("academic" in predicted_sources),
                    "schema_valid": observation.schema_valid,
                    "fallback": observation.used_fallback,
                    "intent_correct": observation.analysis.intent
                    == case.expected_intent,
                    "sources_correct": set(predicted_sources)
                    == set(case.expected_sources),
                    "route_correct": predicted_mode == case.expected_route,
                    "clarification_predicted": observation.analysis.needs_clarification,
                    "clarification_expected": case.clarification_required,
                    "answer_mode_correct": observation.analysis.answer_mode
                    == case.expected_answer_mode,
                    "confidence": observation.analysis.confidence,
                    "analysis_latency_ms": observation.latency_ms,
                    "prompt_tokens": observation.usage.prompt_tokens
                    if observation.usage
                    else None,
                    "completion_tokens": observation.usage.completion_tokens
                    if observation.usage
                    else None,
                }
                row.update(
                    _evaluate_evidence(
                        case, observation.analysis, variant, grader_adapter
                    )
                )
                row.update(_evaluate_citations(case, semantic_adapter))
                accumulator.case_runs.append(row)
            except Exception as exc:
                accumulator.analysis_latency.add_failure(exc)
                accumulator.failures.append(
                    {"case_id": case.case_id, "error_type": type(exc).__name__}
                )
    return _build_report(
        cases,
        accumulator,
        signatures,
        variant=variant,
        runs=runs,
        seed=seed,
        provider_name=provider_name,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        grader_name=grader_name,
        semantic_verifier_name=semantic_verifier_name,
    )


def _variant_prediction(
    variant: GraphVariant,
    adaptive_mode: ExecutionMode,
    adaptive_sources: list[SourceRequirement],
) -> tuple[ExecutionMode, list[SourceRequirement]]:
    fixed: dict[str, tuple[ExecutionMode, list[SourceRequirement]]] = {
        "direct_answer": ("direct_answer", []),
        "local_only": ("local_only", ["local"]),
        "web_only": ("web_only", ["web"]),
        "academic_only": ("academic_only", ["academic"]),
    }
    if variant in fixed:
        return fixed[variant]
    if variant == "single_source_adaptive" and len(adaptive_sources) > 1:
        source = adaptive_sources[0]
        return fixed[f"{source}_only"]
    return adaptive_mode, list(adaptive_sources)


def _evaluate_evidence(
    case: AdaptiveEvaluationCase,
    analysis: QueryAnalysis,
    variant: GraphVariant,
    grader_adapter: ExperimentalLLMEvidenceGrader | None,
) -> dict[str, Any]:
    if case.evidence_expectation == "not_applicable":
        return {}
    grade = grader_adapter.grade if grader_adapter is not None else grade_evidence
    initial = grade(case.question, analysis, case.evidence)
    corrected = (
        grade(case.question, analysis, case.corrected_evidence)
        if case.corrected_evidence
        else initial
    )
    retries = (
        0
        if variant == "correction_disabled"
        else 2
        if variant == "correction_retry_2"
        else 1
    )
    production_trigger = initial.status == "empty" or (
        initial.status == "insufficient" and initial.relevance < 0.3
    )
    correction_capable = variant in {
        "adaptive",
        "single_source_adaptive",
        "multi_source_adaptive",
        "correction_retry_1",
        "correction_retry_2",
    }
    correction_applied = (
        correction_capable
        and retries > 0
        and production_trigger
        and bool(case.corrected_evidence)
    )
    effective = corrected if correction_applied else initial
    correction_attempts = (
        1 + int(retries == 2 and corrected.status != "sufficient")
        if correction_applied
        else 0
    )
    return {
        "evidence_expected": case.evidence_expectation,
        "evidence_predicted": initial.status,
        "evidence_correct": initial.status == case.evidence_expectation,
        "false_sufficient": initial.status == "sufficient"
        and case.evidence_expectation != "sufficient",
        "false_insufficient": initial.status != "sufficient"
        and case.evidence_expectation == "sufficient",
        "missing_aspects_correct": set(initial.missing_aspects)
        == set(case.expected_missing_aspects),
        "conflict_detected": bool(effective.conflicts),
        "initial_relevance": initial.relevance,
        "final_relevance": effective.relevance,
        "initial_coverage": initial.coverage,
        "final_coverage": effective.coverage,
        "correction_applied": correction_applied,
        "correction_attempts": correction_attempts,
        "correction_quality_improved": effective.relevance > initial.relevance
        or effective.coverage > initial.coverage,
        "correction_recovered": initial.status != "sufficient"
        and effective.status == "sufficient",
        "unnecessary_retry": correction_applied and initial.status == "sufficient",
        "extra_latency_ms": case.correction_extra_latency_ms * correction_attempts,
        "extra_llm_calls": case.correction_extra_llm_calls * correction_attempts,
        "extra_mcp_calls": case.correction_extra_mcp_calls * correction_attempts,
    }


def _evaluate_citations(
    case: AdaptiveEvaluationCase,
    semantic_adapter: ExperimentalSemanticVerifier | None,
) -> dict[str, Any]:
    if case.citation_expectation == "not_applicable":
        return {}
    initial = verify_answer(
        case.citation_answer or "", case.local_citations, case.web_sources
    )
    repaired_text = repair_answer_citations(
        case.citation_answer or "", case.local_citations, case.web_sources
    )
    repaired = verify_answer(repaired_text, case.local_citations, case.web_sources)
    triggered = not initial.valid
    expected_initial_valid = case.citation_expectation == "valid"
    expected_repair = case.citation_expectation == "repairable"
    semantic = (
        semantic_adapter.verify(
            case.citation_answer or "", case.local_citations, case.web_sources
        )
        if semantic_adapter is not None
        else None
    )
    return {
        "citation_expected": case.citation_expectation,
        "citation_initial_valid": initial.valid,
        "citation_classification_correct": initial.valid == expected_initial_valid,
        "citation_repair_triggered": triggered,
        "citation_repair_success": triggered and repaired.valid,
        "citation_repair_expected": expected_repair,
        "citation_repair_regression": initial.valid and not repaired.valid,
        "citation_markers_valid": not any(
            "does not exist" in error or "does not reference" in error
            for error in initial.errors
        ),
        "citation_objects_complete": not any(
            "no URL" in error for error in initial.errors
        )
        and not any(
            "no source title" in warning
            or "no page metadata" in warning
            or "limited publication metadata" in warning
            for warning in initial.warnings
        ),
        "hallucinated_citation_detected": any(
            "does not exist" in error for error in initial.errors
        ),
        "missing_citation_detected": any(
            "does not reference" in error for error in initial.errors
        ),
        "semantic_supported_claims": semantic.supported_claims if semantic else None,
        "semantic_evaluated_claims": semantic.evaluated_claims if semantic else None,
    }


def _build_report(
    cases: list[AdaptiveEvaluationCase],
    accumulator: EvaluationAccumulator,
    signatures: dict[str, list[str]],
    *,
    variant: GraphVariant,
    runs: int,
    seed: int,
    provider_name: str,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
    grader_name: str,
    semantic_verifier_name: str,
) -> dict[str, Any]:
    rows = accumulator.case_runs
    query = {
        "schema_valid_rate": _rate(rows, "schema_valid"),
        "fallback_rate": _rate(rows, "fallback"),
        "intent_accuracy": _rate(rows, "intent_correct"),
        "source_selection_accuracy": _rate(rows, "sources_correct"),
        "route_accuracy": _rate(rows, "route_correct"),
        "answer_mode_accuracy": _rate(rows, "answer_mode_correct"),
        "clarification": _binary_metrics(
            rows, "clarification_predicted", "clarification_expected"
        ),
        "confidence_calibration": _confidence_calibration(rows),
        "repeated_run_stability": statistics.fmean(
            1.0 if len(set(values)) == 1 else 0.0 for values in signatures.values()
        ),
        "latency_ms": accumulator.analysis_latency.summary(),
        "token_usage": _token_summary(rows),
    }
    evidence_rows = [row for row in rows if "evidence_correct" in row]
    citation_rows = [row for row in rows if "citation_initial_valid" in row]
    correction_rows = [row for row in evidence_rows if row["correction_applied"]]
    report = {
        "dataset": {
            "case_count": len(cases),
            "categories": dict(Counter(case.category for case in cases)),
        },
        "configuration": {
            "variant": variant,
            "runs": runs,
            "seed": seed,
            "provider": provider_name,
            "temperature": 0 if provider_name != "deterministic" else None,
            "human_golden_labels_primary": True,
            "grader": grader_name,
            "semantic_verifier": semantic_verifier_name,
        },
        "query_analysis": query,
        "evidence_grading": {
            "accuracy": _rate(evidence_rows, "evidence_correct"),
            "classification": _multiclass_metrics(
                evidence_rows, "evidence_predicted", "evidence_expected"
            ),
            "false_sufficient_rate": _rate(evidence_rows, "false_sufficient"),
            "false_insufficient_rate": _rate(evidence_rows, "false_insufficient"),
            "missing_aspect_accuracy": _rate(evidence_rows, "missing_aspects_correct"),
            "conflict_detection_rate": _rate(
                [
                    row
                    for row in evidence_rows
                    if row["evidence_expected"] == "conflicting"
                ],
                "conflict_detected",
            ),
        },
        "corrective_retrieval": {
            "evaluated_runs": len(correction_rows),
            "relevance_gain_mean": _mean_delta(
                correction_rows, "initial_relevance", "final_relevance"
            ),
            "coverage_gain_mean": _mean_delta(
                correction_rows, "initial_coverage", "final_coverage"
            ),
            "successful_recovery_rate": _rate(correction_rows, "correction_recovered"),
            "unnecessary_retry_rate": _rate(correction_rows, "unnecessary_retry"),
            "extra_latency_ms_mean": _mean(correction_rows, "extra_latency_ms"),
            "extra_llm_calls": sum(row["extra_llm_calls"] for row in correction_rows),
            "extra_mcp_calls": sum(row["extra_mcp_calls"] for row in correction_rows),
        },
        "citations": {
            "evaluated_runs": len(citation_rows),
            "classification_accuracy": _rate(
                citation_rows, "citation_classification_correct"
            ),
            "marker_validity_rate": _rate(citation_rows, "citation_markers_valid"),
            "citation_object_completeness_rate": _rate(
                citation_rows, "citation_objects_complete"
            ),
            "missing_citation_rate": _rate(citation_rows, "missing_citation_detected"),
            "hallucinated_citation_rate": _rate(
                citation_rows, "hallucinated_citation_detected"
            ),
            "repair_trigger_rate": _rate(citation_rows, "citation_repair_triggered"),
            "repair_success_rate": _rate(
                [row for row in citation_rows if row["citation_repair_triggered"]],
                "citation_repair_success",
            ),
            "repair_regression_rate": _rate(
                citation_rows, "citation_repair_regression"
            ),
            "hallucinated_marker_detection_rate": _rate(
                [
                    row
                    for row in citation_rows
                    if row["citation_expected"] == "repairable"
                ],
                "hallucinated_citation_detected",
            ),
            "missing_marker_detection_rate": _rate(
                citation_rows, "missing_citation_detected"
            ),
            "semantic_support_rate": _semantic_support_rate(citation_rows),
        },
        "cost": _cost_summary(rows, input_cost_per_million, output_cost_per_million),
        "graph_variant": _graph_variant_summary(rows, accumulator.failures),
        "failures": {
            "count": len(accumulator.failures),
            "types": dict(Counter(item["error_type"] for item in accumulator.failures)),
        },
        "case_runs": rows,
    }
    return report


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    return sum(bool(row.get(key)) for row in rows) / len(rows) if rows else None


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return statistics.fmean(values) if values else None


def _mean_delta(rows: list[dict[str, Any]], before: str, after: str) -> float | None:
    values = [float(row[after]) - float(row[before]) for row in rows]
    return statistics.fmean(values) if values else None


def _binary_metrics(
    rows: list[dict[str, Any]], predicted: str, expected: str
) -> dict[str, float | None]:
    tp = sum(bool(row[predicted]) and bool(row[expected]) for row in rows)
    fp = sum(bool(row[predicted]) and not bool(row[expected]) for row in rows)
    fn = sum(not bool(row[predicted]) and bool(row[expected]) for row in rows)
    return {
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _multiclass_metrics(
    rows: list[dict[str, Any]], predicted: str, expected: str
) -> dict[str, dict[str, float | None]]:
    labels = ["sufficient", "insufficient", "conflicting", "empty"]
    output: dict[str, dict[str, float | None]] = {}
    for label in labels:
        tp = sum(row[predicted] == label and row[expected] == label for row in rows)
        fp = sum(row[predicted] == label and row[expected] != label for row in rows)
        fn = sum(row[predicted] != label and row[expected] == label for row in rows)
        output[label] = {
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        }
    return output


def _confidence_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bins: dict[str, list[bool]] = {"0.0-0.5": [], "0.5-0.8": [], "0.8-1.0": []}
    for row in rows:
        confidence = float(row["confidence"])
        key = (
            "0.0-0.5"
            if confidence < 0.5
            else "0.5-0.8"
            if confidence < 0.8
            else "0.8-1.0"
        )
        bins[key].append(
            bool(
                row["intent_correct"]
                and row["sources_correct"]
                and row["route_correct"]
            )
        )
    return {
        key: {
            "count": len(values),
            "accuracy": sum(values) / len(values) if values else None,
        }
        for key, values in bins.items()
    }


def _token_summary(rows: list[dict[str, Any]]) -> dict[str, int | None]:
    prompt = [
        row["prompt_tokens"] for row in rows if row.get("prompt_tokens") is not None
    ]
    completion = [
        row["completion_tokens"]
        for row in rows
        if row.get("completion_tokens") is not None
    ]
    return {
        "prompt_tokens": sum(prompt) if prompt else None,
        "completion_tokens": sum(completion) if completion else None,
    }


def _semantic_support_rate(rows: list[dict[str, Any]]) -> float | None:
    supported = sum(
        int(row["semantic_supported_claims"])
        for row in rows
        if row.get("semantic_supported_claims") is not None
    )
    evaluated = sum(
        int(row["semantic_evaluated_claims"])
        for row in rows
        if row.get("semantic_evaluated_claims") is not None
    )
    return supported / evaluated if evaluated else None


def _cost_summary(
    rows: list[dict[str, Any]],
    input_rate: float | None,
    output_rate: float | None,
) -> dict[str, Any]:
    tokens = _token_summary(rows)
    if input_rate is None or output_rate is None or tokens["prompt_tokens"] is None:
        return {
            "estimated_usd": None,
            "reason": "Pricing was not supplied or Provider usage was unavailable.",
        }
    estimated = (
        tokens["prompt_tokens"] * input_rate
        + (tokens["completion_tokens"] or 0) * output_rate
    ) / 1_000_000
    return {
        "estimated_usd": estimated,
        "input_per_million": input_rate,
        "output_per_million": output_rate,
    }


def _graph_variant_summary(
    rows: list[dict[str, Any]], failures: list[dict[str, str]]
) -> dict[str, Any]:
    correctness = [
        bool(
            row["intent_correct"]
            and row["sources_correct"]
            and row["route_correct"]
            and row["answer_mode_correct"]
        )
        for row in rows
    ]
    latency = MeasurementSeries()
    for row in rows:
        latency.add_success(
            float(row["analysis_latency_ms"]) + float(row.get("extra_latency_ms", 0))
        )
    provider_calls = sum(bool(row["analysis_llm_call"]) for row in rows)
    synthesis_calls = sum(not bool(row["clarification_predicted"]) for row in rows)
    return {
        "answer_correctness_proxy": sum(correctness) / len(correctness)
        if correctness
        else None,
        "latency_proxy_ms": latency.summary(),
        "perceived_latency_ms": None,
        "estimated_llm_call_count": provider_calls + synthesis_calls,
        "estimated_mcp_call_count": sum(
            int(row.get("base_mcp_calls", 0)) + int(row.get("extra_mcp_calls", 0))
            for row in rows
        ),
        "token_usage": _token_summary(rows),
        "failure_rate": len(failures) / (len(rows) + len(failures))
        if rows or failures
        else None,
        "note": (
            "Offline path-quality proxy; synthesis correctness, perceived TTFT, and "
            "base retrieval calls require an end-to-end Provider benchmark."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    query = report["query_analysis"]
    evidence = report["evidence_grading"]
    correction = report["corrective_retrieval"]
    citations = report["citations"]
    return "\n".join(
        [
            "# Adaptive Graph Evaluation",
            "",
            f"- Cases: {report['dataset']['case_count']}",
            f"- Variant: `{report['configuration']['variant']}`",
            f"- Runs per case: {report['configuration']['runs']}",
            f"- Provider: `{report['configuration']['provider']}`",
            "",
            "## Query Analysis",
            f"- Schema valid rate: {_display(query['schema_valid_rate'])}",
            f"- Fallback rate: {_display(query['fallback_rate'])}",
            f"- Intent accuracy: {_display(query['intent_accuracy'])}",
            f"- Source-selection accuracy: {_display(query['source_selection_accuracy'])}",
            f"- Route accuracy: {_display(query['route_accuracy'])}",
            f"- Stability: {_display(query['repeated_run_stability'])}",
            "",
            "## Evidence Grading",
            f"- Accuracy: {_display(evidence['accuracy'])}",
            f"- False sufficient rate: {_display(evidence['false_sufficient_rate'])}",
            f"- False insufficient rate: {_display(evidence['false_insufficient_rate'])}",
            "",
            "## Corrective Retrieval",
            f"- Recovery rate: {_display(correction['successful_recovery_rate'])}",
            f"- Relevance gain: {_display(correction['relevance_gain_mean'])}",
            f"- Coverage gain: {_display(correction['coverage_gain_mean'])}",
            f"- Extra latency mean: {correction['extra_latency_ms_mean']}",
            "",
            "## Citations",
            f"- Classification accuracy: {_display(citations['classification_accuracy'])}",
            f"- Repair trigger rate: {_display(citations['repair_trigger_rate'])}",
            f"- Repair success rate: {_display(citations['repair_success_rate'])}",
            f"- Semantic support rate: {citations['semantic_support_rate']}",
            "",
            "Human golden labels are primary. Semantic support is not inferred by the structural verifier.",
        ]
    )


def write_reports(
    report: dict[str, Any], *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report) + "\n", encoding="utf-8")


def _display(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"
