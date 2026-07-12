from __future__ import annotations

import json
import statistics
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.adaptive_graph import observe_analysis
from app.graphs.adaptive import (
    AnswerMode,
    EvidenceItem,
    EvidenceStatus,
    ExecutionMode,
    QueryIntent,
    QueryAnalysis,
    SourceRequirement,
    build_execution_plan,
    build_query_analysis_prompt,
    grade_evidence,
    parse_query_analysis_response,
    verify_answer,
)
from app.llm.providers import LLMProvider, TokenUsage
from app.reliability.reporting import MeasurementSeries

ClaimLabel = Literal[
    "supported",
    "partially_supported",
    "unsupported",
    "contradicted",
    "common_knowledge",
    "reasoning_only",
]
CLAIM_LABEL_VALUES = {
    "supported",
    "partially_supported",
    "unsupported",
    "contradicted",
    "common_knowledge",
    "reasoning_only",
}
VerifierDecision = Literal[
    "keep deterministic only",
    "enable semantic verifier for high-risk cases",
    "enable semantic verifier globally",
    "collect more data before decision",
]


class HeldOutCase(BaseModel):
    """Unlabelled model input. Golden expectations live in another file."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^ho_[a-z0-9_]+$")
    category: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1_000)
    selected_book_count: int = Field(default=0, ge=0, le=20)
    has_conversation_context: bool = False
    evidence: list[EvidenceItem] = Field(default_factory=list)
    provider_failure: str | None = Field(default=None, max_length=80)


class EvidenceHumanLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    relevance: Literal["high", "medium", "low", "none"]
    authority: Literal["high", "medium", "low", "unknown"]
    freshness: Literal["current", "acceptable", "stale", "unknown"]
    duplicate: bool = False
    contradiction: bool = False
    citation_ready: bool
    needs_fetch: bool = False
    answers_subquery: bool


class HeldOutLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    expected_intent: QueryIntent
    expected_sources: list[SourceRequirement] = Field(default_factory=list)
    expected_route: ExecutionMode
    clarification_required: bool
    expected_answer_mode: AnswerMode
    expected_evidence_status: EvidenceStatus
    grade_applicable: bool = False
    expected_missing_aspects: list[str] = Field(default_factory=list)
    evidence_labels: list[EvidenceHumanLabel] = Field(default_factory=list)


class ClaimAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^claim_[a-z0-9_]+$")
    case_id: str
    claim: str = Field(min_length=1, max_length=1_500)
    citation_id: str | None = None
    source_type: Literal["local", "web", "academic"] | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_excerpt: str | None = Field(default=None, max_length=4_000)
    label: ClaimLabel
    support_strength: float = Field(ge=0, le=1)
    missing_citation: bool = False
    wrong_source: bool = False

    @model_validator(mode="after")
    def citation_metadata_is_consistent(self) -> "ClaimAnnotation":
        if self.citation_id and not self.source_type:
            raise ValueError("source_type is required for cited claims")
        return self


@dataclass
class HeldOutBundle:
    cases: list[HeldOutCase]
    labels: dict[str, HeldOutLabel]
    claims: list[ClaimAnnotation]


def load_heldout_bundle(
    case_path: Path, label_path: Path, claim_path: Path
) -> HeldOutBundle:
    cases = _load_jsonl(case_path, HeldOutCase)
    labels = _load_jsonl(label_path, HeldOutLabel)
    claims = _load_jsonl(claim_path, ClaimAnnotation)
    case_ids = {case.case_id for case in cases}
    label_ids = {label.case_id for label in labels}
    if len(case_ids) != len(cases) or len(label_ids) != len(labels):
        raise ValueError("Held-out case and label IDs must be unique")
    if case_ids != label_ids:
        raise ValueError("Held-out cases and labels must have identical IDs")
    unknown_claims = sorted({claim.case_id for claim in claims}.difference(case_ids))
    if unknown_claims:
        raise ValueError("Claim annotations reference unknown held-out cases")
    return HeldOutBundle(
        cases=cases,
        labels={label.case_id: label for label in labels},
        claims=claims,
    )


def _load_jsonl(path: Path, model: type[BaseModel]) -> list[Any]:
    output: list[Any] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            output.append(model.model_validate_json(line))
        except Exception as exc:
            raise ValueError(
                f"Invalid held-out data at {path.name}:{line_number}"
            ) from exc
    if not output:
        raise ValueError(f"Held-out data is empty: {path.name}")
    return output


@dataclass
class ClaimVerifierObservation:
    classification: ClaimLabel | None
    latency_ms: float
    usage: TokenUsage | None
    failure_type: str | None = None


class ClaimSemanticVerifier:
    """Evaluation-only claim judge. Labels are never included in its prompt."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def evaluate(self, annotation: ClaimAnnotation) -> ClaimVerifierObservation:
        method = getattr(self.provider, "generate_structured", None)
        if not callable(method):
            return ClaimVerifierObservation(None, 0, None, "UnsupportedProvider")
        prompt = json.dumps(
            {
                "task": (
                    "Classify whether the source supports the claim. Return JSON with "
                    "classification only: supported, partially_supported, unsupported, "
                    "contradicted, common_knowledge, or reasoning_only."
                ),
                "claim": annotation.claim,
                "citation_id": annotation.citation_id,
                "source_title": annotation.source_title,
                "source_url": annotation.source_url,
                "source_excerpt": annotation.source_excerpt,
            },
            ensure_ascii=False,
        )
        started = perf_counter()
        try:
            result = method(prompt, temperature=0)
            payload = json.loads(result.text)
            classification = payload.get("classification")
            if classification not in CLAIM_LABEL_VALUES:
                raise ValueError("Unknown semantic classification")
            return ClaimVerifierObservation(
                classification=classification,
                latency_ms=(perf_counter() - started) * 1_000,
                usage=result.usage,
            )
        except Exception as exc:
            return ClaimVerifierObservation(
                None, (perf_counter() - started) * 1_000, None, type(exc).__name__
            )


def benchmark_query_temperatures(
    bundle: HeldOutBundle,
    *,
    provider: LLMProvider,
    runs: int,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> dict[str, Any]:
    method = getattr(provider, "generate_structured", None)
    if not callable(method):
        raise ValueError("Provider does not support structured generation")
    output: dict[str, Any] = {}
    # Production QueryAnalysis currently uses temperature zero; both entries are
    # retained so future production-temperature changes remain measurable.
    for name, temperature in (("temperature_zero", 0.0), ("production", 0.0)):
        rows: list[dict[str, Any]] = []
        latency = MeasurementSeries()
        signatures: dict[str, list[str]] = {case.case_id: [] for case in bundle.cases}
        for case in bundle.cases:
            label = bundle.labels[case.case_id]
            prompt = build_query_analysis_prompt(
                case.question,
                case.selected_book_count,
                case.has_conversation_context,
            )
            for _ in range(runs):
                started = perf_counter()
                try:
                    result = method(prompt, temperature=temperature)
                    analysis = QueryAnalysis.model_validate(
                        parse_query_analysis_response(result.text)
                    )
                    elapsed = (perf_counter() - started) * 1_000
                    latency.add_success(elapsed)
                    plan = build_execution_plan(analysis)
                    signature = json.dumps(
                        {
                            "intent": analysis.intent,
                            "sources": analysis.required_sources,
                            "route": plan.mode,
                            "clarification": analysis.needs_clarification,
                        },
                        sort_keys=True,
                    )
                    signatures[case.case_id].append(signature)
                    rows.append(
                        {
                            "schema_valid": True,
                            "intent_correct": analysis.intent == label.expected_intent,
                            "sources_correct": set(analysis.required_sources)
                            == set(label.expected_sources),
                            "route_correct": plan.mode == label.expected_route,
                            "clarification_predicted": analysis.needs_clarification,
                            "clarification_expected": label.clarification_required,
                            "confidence": analysis.confidence,
                            "prompt_tokens": result.usage.prompt_tokens
                            if result.usage
                            else None,
                            "completion_tokens": result.usage.completion_tokens
                            if result.usage
                            else None,
                        }
                    )
                except Exception as exc:
                    latency.add_failure(exc)
                    rows.append(
                        {
                            "schema_valid": False,
                            "intent_correct": False,
                            "sources_correct": False,
                            "route_correct": False,
                            "clarification_predicted": False,
                            "clarification_expected": label.clarification_required,
                            "confidence": 0,
                            "prompt_tokens": None,
                            "completion_tokens": None,
                        }
                    )
        output[name] = {
            "case_count": len(bundle.cases),
            "runs_per_case": runs,
            "temperature": temperature,
            "schema_valid_rate": _rate(rows, "schema_valid"),
            "fallback_rate": 1 - (_rate(rows, "schema_valid") or 0),
            "intent_accuracy": _rate(rows, "intent_correct"),
            "required_sources_accuracy": _rate(rows, "sources_correct"),
            "route_accuracy": _rate(rows, "route_correct"),
            "clarification": _binary_metrics(
                rows, "clarification_predicted", "clarification_expected"
            ),
            "stability": statistics.fmean(
                1.0 if values and len(set(values)) == 1 else 0.0
                for values in signatures.values()
            ),
            "confidence_calibration": _confidence_calibration(rows),
            "latency_ms": latency.summary(),
            "token_usage": _token_usage(rows, "prompt_tokens", "completion_tokens"),
            "estimated_cost": _estimated_cost(
                rows,
                "prompt_tokens",
                "completion_tokens",
                input_cost_per_million,
                output_cost_per_million,
            ),
        }
    return output


@dataclass
class HeldOutAccumulator:
    rows: list[dict[str, Any]] = field(default_factory=list)
    claim_rows: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    analysis_latency: MeasurementSeries = field(default_factory=MeasurementSeries)
    semantic_latency: MeasurementSeries = field(default_factory=MeasurementSeries)


def evaluate_heldout(
    bundle: HeldOutBundle,
    *,
    runs: int,
    provider: LLMProvider | None = None,
    provider_name: str = "deterministic",
    semantic_provider: LLMProvider | None = None,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be positive")
    accumulator = HeldOutAccumulator()
    signatures: dict[str, list[str]] = {case.case_id: [] for case in bundle.cases}
    for case in bundle.cases:
        label = bundle.labels[case.case_id]
        for run_index in range(runs):
            try:
                observation = observe_analysis(
                    _stage58_case(case, label),
                    provider=provider,
                    provider_name=provider_name,
                )
                accumulator.analysis_latency.add_success(observation.latency_ms)
                plan = build_execution_plan(observation.analysis)
                grade = grade_evidence(
                    case.question, observation.analysis, case.evidence
                )
                signature = json.dumps(
                    {
                        "intent": observation.analysis.intent,
                        "sources": observation.analysis.required_sources,
                        "route": plan.mode,
                        "clarification": observation.analysis.needs_clarification,
                    },
                    sort_keys=True,
                )
                signatures[case.case_id].append(signature)
                accumulator.rows.append(
                    {
                        "request_id": str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"pla-stage59:{case.case_id}:{run_index}",
                            )
                        ),
                        "case_id": case.case_id,
                        "route": plan.mode,
                        "schema_valid": observation.schema_valid,
                        "fallback": observation.used_fallback,
                        "intent_correct": observation.analysis.intent
                        == label.expected_intent,
                        "sources_correct": set(observation.analysis.required_sources)
                        == set(label.expected_sources),
                        "route_correct": plan.mode == label.expected_route,
                        "clarification_predicted": observation.analysis.needs_clarification,
                        "clarification_expected": label.clarification_required,
                        "confidence": observation.analysis.confidence,
                        "grade_predicted": grade.status,
                        "grade_expected": label.expected_evidence_status,
                        "grade_applicable": label.grade_applicable,
                        "missing_aspects_correct": set(grade.missing_aspects)
                        == set(label.expected_missing_aspects),
                        "analysis_latency_ms": observation.latency_ms,
                        "prompt_tokens": observation.usage.prompt_tokens
                        if observation.usage
                        else None,
                        "completion_tokens": observation.usage.completion_tokens
                        if observation.usage
                        else None,
                    }
                )
            except Exception as exc:
                accumulator.analysis_latency.add_failure(exc)
                accumulator.failures.append(type(exc).__name__)
    verifier = ClaimSemanticVerifier(semantic_provider) if semantic_provider else None
    for annotation in bundle.claims:
        structural_problem = _structural_problem(annotation)
        semantic = verifier.evaluate(annotation) if verifier else None
        if semantic is not None:
            if semantic.failure_type:
                accumulator.semantic_latency.add_failure(
                    RuntimeError(semantic.failure_type)
                )
            else:
                accumulator.semantic_latency.add_success(semantic.latency_ms)
        semantic_problem = (
            _is_problem_label(semantic.classification)
            if semantic and semantic.classification
            else None
        )
        accumulator.claim_rows.append(
            {
                "claim_id": annotation.claim_id,
                "case_id": annotation.case_id,
                "expected_problem": _is_problem_label(annotation.label),
                "expected_label": annotation.label,
                "structural_problem": structural_problem,
                "semantic_problem": semantic_problem,
                "semantic_label": semantic.classification if semantic else None,
                "combined_problem": structural_problem or bool(semantic_problem),
                "semantic_prompt_tokens": semantic.usage.prompt_tokens
                if semantic and semantic.usage
                else None,
                "semantic_completion_tokens": semantic.usage.completion_tokens
                if semantic and semantic.usage
                else None,
            }
        )
    return _heldout_report(
        bundle,
        accumulator,
        signatures,
        provider_name=provider_name,
        runs=runs,
        semantic_enabled=semantic_provider is not None,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
    )


def _stage58_case(case: HeldOutCase, label: HeldOutLabel):
    from app.evaluation.adaptive_graph import AdaptiveEvaluationCase

    return AdaptiveEvaluationCase(
        case_id=case.case_id.removeprefix("ho_"),
        category=case.category,
        question=case.question,
        selected_book_count=case.selected_book_count,
        has_conversation_context=case.has_conversation_context,
        expected_intent=label.expected_intent,
        expected_sources=label.expected_sources,
        expected_route=label.expected_route,
        clarification_required=label.clarification_required,
        expected_answer_mode=label.expected_answer_mode,
    )


def _structural_problem(annotation: ClaimAnnotation) -> bool:
    marker = f"[{annotation.citation_id}]" if annotation.citation_id else ""
    answer = f"{annotation.claim} {marker}".strip()
    local: list[dict[str, Any]] = []
    web: list[dict[str, Any]] = []
    if annotation.citation_id and annotation.source_type == "local":
        local.append(
            {
                "citation_id": annotation.citation_id,
                "document_title": annotation.source_title or "Local source",
                "page_start": 1,
            }
        )
    elif annotation.citation_id:
        web.append(
            {
                "source_id": annotation.citation_id,
                "title": annotation.source_title or "External source",
                "url": annotation.source_url or "",
                "source_type": annotation.source_type,
                "authors": ["Unknown"] if annotation.source_type == "academic" else [],
            }
        )
    result = verify_answer(answer, local, web)
    return not result.valid or annotation.missing_citation or annotation.wrong_source


def _is_problem_label(label: ClaimLabel | None) -> bool:
    return label in {"partially_supported", "unsupported", "contradicted"}


def confusion_metrics(
    rows: list[dict[str, Any]], *, prediction_key: str
) -> dict[str, float | int | None]:
    evaluated = [row for row in rows if row.get(prediction_key) is not None]
    tp = sum(
        bool(row[prediction_key]) and bool(row["expected_problem"]) for row in evaluated
    )
    fp = sum(
        bool(row[prediction_key]) and not bool(row["expected_problem"])
        for row in evaluated
    )
    tn = sum(
        not bool(row[prediction_key]) and not bool(row["expected_problem"])
        for row in evaluated
    )
    fn = sum(
        not bool(row[prediction_key]) and bool(row["expected_problem"])
        for row in evaluated
    )
    return {
        "evaluated": len(evaluated),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
    }


def multiclass_confusion(
    rows: list[dict[str, Any]], predicted: str, expected: str
) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for row in rows:
        expected_value = str(row[expected])
        predicted_value = str(row[predicted])
        output.setdefault(expected_value, {})[predicted_value] = (
            output.setdefault(expected_value, {}).get(predicted_value, 0) + 1
        )
    return output


def _heldout_report(
    bundle: HeldOutBundle,
    accumulator: HeldOutAccumulator,
    signatures: dict[str, list[str]],
    *,
    provider_name: str,
    runs: int,
    semantic_enabled: bool,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> dict[str, Any]:
    rows = accumulator.rows
    grade_rows = [row for row in rows if row["grade_applicable"]]
    claims = accumulator.claim_rows
    structural = confusion_metrics(claims, prediction_key="structural_problem")
    semantic = confusion_metrics(claims, prediction_key="semantic_problem")
    combined = confusion_metrics(claims, prediction_key="combined_problem")
    decision = _production_decision(semantic, accumulator.semantic_latency)
    evidence_quality = _evidence_quality(bundle)
    return {
        "dataset": {
            "case_count": len(bundle.cases),
            "claim_count": len(bundle.claims),
            "input_and_labels_separated": True,
        },
        "configuration": {
            "provider": provider_name,
            "runs": runs,
            "semantic_verifier_enabled": semantic_enabled,
            "human_labels_primary": True,
        },
        "query_analysis": {
            "schema_valid_rate": _rate(rows, "schema_valid"),
            "fallback_rate": _rate(rows, "fallback"),
            "intent_accuracy": _rate(rows, "intent_correct"),
            "required_sources_accuracy": _rate(rows, "sources_correct"),
            "route_accuracy": _rate(rows, "route_correct"),
            "clarification": _binary_metrics(
                rows, "clarification_predicted", "clarification_expected"
            ),
            "stability": statistics.fmean(
                1.0 if len(set(values)) == 1 else 0.0 for values in signatures.values()
            ),
            "confidence_calibration": _confidence_calibration(rows),
            "latency_ms": accumulator.analysis_latency.summary(),
            "token_usage": _token_usage(rows, "prompt_tokens", "completion_tokens"),
            "estimated_cost": _estimated_cost(
                rows,
                "prompt_tokens",
                "completion_tokens",
                input_cost_per_million,
                output_cost_per_million,
            ),
        },
        "mcp_evidence_quality": evidence_quality,
        "deterministic_grader": {
            "accuracy": _rate(
                [
                    {"correct": row["grade_predicted"] == row["grade_expected"]}
                    for row in grade_rows
                ],
                "correct",
            ),
            "confusion_matrix": multiclass_confusion(
                grade_rows, "grade_predicted", "grade_expected"
            ),
            "false_sufficient_rate": _conditional_rate(
                grade_rows,
                lambda row: (
                    row["grade_predicted"] == "sufficient"
                    and row["grade_expected"] != "sufficient"
                ),
            ),
            "false_insufficient_rate": _conditional_rate(
                grade_rows,
                lambda row: (
                    row["grade_predicted"] != "sufficient"
                    and row["grade_expected"] == "sufficient"
                ),
            ),
            "conflict_miss_rate": _conditional_rate(
                [row for row in grade_rows if row["grade_expected"] == "conflicting"],
                lambda row: row["grade_predicted"] != "conflicting",
            ),
        },
        "claim_annotations": {
            "label_distribution": dict(Counter(claim.label for claim in bundle.claims)),
            "support_rate": _human_support_rate(bundle.claims),
            "missing_citation_rate": sum(
                claim.missing_citation for claim in bundle.claims
            )
            / len(bundle.claims),
            "wrong_source_rate": sum(claim.wrong_source for claim in bundle.claims)
            / len(bundle.claims),
            "hallucinated_citation_rate": sum(
                bool(claim.citation_id)
                and (
                    claim.wrong_source or claim.label in {"unsupported", "contradicted"}
                )
                for claim in bundle.claims
            )
            / len(bundle.claims),
        },
        "verifiers": {
            "deterministic": structural,
            "semantic": semantic,
            "combined": combined,
            "semantic_latency_ms": accumulator.semantic_latency.summary(),
            "semantic_token_usage": _token_usage(
                claims, "semantic_prompt_tokens", "semantic_completion_tokens"
            ),
            "semantic_cost": _estimated_cost(
                claims,
                "semantic_prompt_tokens",
                "semantic_completion_tokens",
                input_cost_per_million,
                output_cost_per_million,
            ),
            "semantic_llm_call_count": int(
                accumulator.semantic_latency.summary()["count"]
            ),
            "semantic_class_detection": {
                label: _class_recall(claims, label)
                for label in (
                    "partially_supported",
                    "unsupported",
                    "contradicted",
                    "common_knowledge",
                    "reasoning_only",
                )
            },
        },
        "failures": {
            "count": len(accumulator.failures),
            "types": dict(Counter(accumulator.failures)),
        },
        "failure_case_analysis": {
            "query_error_categories": dict(
                Counter(
                    case.category
                    for case in bundle.cases
                    if any(
                        row["case_id"] == case.case_id
                        and not (
                            row["intent_correct"]
                            and row["sources_correct"]
                            and row["route_correct"]
                        )
                        for row in rows
                    )
                )
            ),
            "grader_errors": dict(
                Counter(
                    f"{row['grade_expected']}->{row['grade_predicted']}"
                    for row in grade_rows
                    if row["grade_expected"] != row["grade_predicted"]
                )
            ),
            "deterministic_verifier_errors": dict(
                Counter(
                    row["expected_label"]
                    for row in claims
                    if bool(row["structural_problem"]) != bool(row["expected_problem"])
                )
            ),
            "semantic_verifier_errors": dict(
                Counter(
                    f"{row['expected_label']}->{row['semantic_label']}"
                    for row in claims
                    if row["semantic_label"] is not None
                    and row["semantic_label"] != row["expected_label"]
                )
            ),
        },
        "production_recommendation": decision,
        "case_runs": rows,
        "claim_runs": [
            {
                key: row[key]
                for key in (
                    "claim_id",
                    "case_id",
                    "expected_problem",
                    "structural_problem",
                    "semantic_problem",
                    "combined_problem",
                )
            }
            for row in claims
        ],
    }


def _evidence_quality(bundle: HeldOutBundle) -> dict[str, Any]:
    labels = [
        label for item in bundle.labels.values() for label in item.evidence_labels
    ]
    evidence_count = sum(len(case.evidence) for case in bundle.cases)
    return {
        "sample_count": evidence_count,
        "human_label_count": len(labels),
        "relevant_rate": sum(label.relevance in {"high", "medium"} for label in labels)
        / len(labels)
        if labels
        else None,
        "high_authority_rate": sum(label.authority == "high" for label in labels)
        / len(labels)
        if labels
        else None,
        "stale_rate": sum(label.freshness == "stale" for label in labels) / len(labels)
        if labels
        else None,
        "duplication_rate": sum(label.duplicate for label in labels) / len(labels)
        if labels
        else None,
        "contradiction_rate": sum(label.contradiction for label in labels) / len(labels)
        if labels
        else None,
        "citation_ready_rate": sum(label.citation_ready for label in labels)
        / len(labels)
        if labels
        else None,
        "needs_fetch_rate": sum(label.needs_fetch for label in labels) / len(labels)
        if labels
        else None,
        "answers_subquery_rate": sum(label.answers_subquery for label in labels)
        / len(labels)
        if labels
        else None,
        "real_provider_collection": False,
        "provider_success_rate": None,
        "fallback_rate": None,
        "deduplication_rate": None,
        "latency_ms": None,
        "cost_per_valid_evidence": None,
    }


def _production_decision(
    semantic: dict[str, float | int | None], latency: MeasurementSeries
) -> VerifierDecision:
    if int(semantic["evaluated"] or 0) < 30:
        return "collect more data before decision"
    precision = semantic["precision"]
    recall = semantic["recall"]
    false_positive = semantic["false_positive_rate"]
    latency_summary = latency.summary()
    p95 = latency_summary["p95"]
    if (
        precision is not None
        and recall is not None
        and false_positive is not None
        and p95 is not None
        and precision >= 0.95
        and recall >= 0.9
        and false_positive <= 0.05
        and p95 <= 1_000
    ):
        return "enable semantic verifier globally"
    if (
        precision is not None
        and recall is not None
        and false_positive is not None
        and precision >= 0.9
        and recall >= 0.75
        and false_positive <= 0.1
    ):
        return "enable semantic verifier for high-risk cases"
    return "keep deterministic only"


def render_heldout_markdown(report: dict[str, Any]) -> str:
    query = report["query_analysis"]
    grader = report["deterministic_grader"]
    verifiers = report["verifiers"]
    return "\n".join(
        [
            "# Held-out Research Quality Evaluation",
            "",
            f"- Held-out cases: {report['dataset']['case_count']}",
            f"- Claim annotations: {report['dataset']['claim_count']}",
            f"- Provider: `{report['configuration']['provider']}`",
            "",
            "## Query Analysis",
            f"- Schema valid rate: {_display(query['schema_valid_rate'])}",
            f"- Intent accuracy: {_display(query['intent_accuracy'])}",
            f"- Route accuracy: {_display(query['route_accuracy'])}",
            f"- Stability: {_display(query['stability'])}",
            "",
            "## Evidence and Grader",
            f"- Deterministic grader accuracy: {_display(grader['accuracy'])}",
            f"- False sufficient rate: {_display(grader['false_sufficient_rate'])}",
            f"- Conflict miss rate: {_display(grader['conflict_miss_rate'])}",
            "",
            "## Claim Support",
            f"- Deterministic precision: {_display(verifiers['deterministic']['precision'])}",
            f"- Deterministic recall: {_display(verifiers['deterministic']['recall'])}",
            f"- Semantic precision: {_display(verifiers['semantic']['precision'])}",
            f"- Semantic recall: {_display(verifiers['semantic']['recall'])}",
            "",
            f"## Production recommendation: {report['production_recommendation']}",
            "",
            "Held-out labels are human-authored and are never inserted into model prompts.",
        ]
    )


def write_heldout_reports(
    report: dict[str, Any], *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_heldout_markdown(report) + "\n", encoding="utf-8")


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    return sum(bool(row.get(key)) for row in rows) / len(rows) if rows else None


def _conditional_rate(rows: list[dict[str, Any]], predicate) -> float | None:
    return sum(bool(predicate(row)) for row in rows) / len(rows) if rows else None


def _binary_metrics(rows, predicted, expected):
    tp = sum(bool(row[predicted]) and bool(row[expected]) for row in rows)
    fp = sum(bool(row[predicted]) and not bool(row[expected]) for row in rows)
    fn = sum(not bool(row[predicted]) and bool(row[expected]) for row in rows)
    return {
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _confidence_calibration(rows):
    bins = {"0.0-0.5": [], "0.5-0.8": [], "0.8-1.0": []}
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


def _token_usage(rows, prompt_key, completion_key):
    prompt = [row[prompt_key] for row in rows if row.get(prompt_key) is not None]
    completion = [
        row[completion_key] for row in rows if row.get(completion_key) is not None
    ]
    return {
        "prompt_tokens": sum(prompt) if prompt else None,
        "completion_tokens": sum(completion) if completion else None,
    }


def _estimated_cost(rows, prompt_key, completion_key, input_rate, output_rate):
    usage = _token_usage(rows, prompt_key, completion_key)
    if input_rate is None or output_rate is None or usage["prompt_tokens"] is None:
        return {"estimated_usd": None, "reason": "Pricing or token usage unavailable."}
    return {
        "estimated_usd": (
            usage["prompt_tokens"] * input_rate
            + (usage["completion_tokens"] or 0) * output_rate
        )
        / 1_000_000
    }


def _human_support_rate(claims: list[ClaimAnnotation]) -> float:
    factual = [
        claim
        for claim in claims
        if claim.label not in {"common_knowledge", "reasoning_only"}
    ]
    return sum(claim.label == "supported" for claim in factual) / len(factual)


def _class_recall(rows: list[dict[str, Any]], label: str) -> float | None:
    expected = [row for row in rows if row["expected_label"] == label]
    if not expected or not any(row["semantic_label"] is not None for row in expected):
        return None
    return sum(row["semantic_label"] == label for row in expected) / len(expected)


def _display(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"
