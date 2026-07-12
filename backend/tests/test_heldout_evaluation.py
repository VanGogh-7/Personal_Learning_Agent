import json
import subprocess
import sys
from pathlib import Path

import pytest

import app.evaluation.heldout as heldout_module
from app.evaluation.adaptive_graph import load_dataset
from app.evaluation.heldout import (
    ClaimSemanticVerifier,
    benchmark_query_temperatures,
    confusion_metrics,
    evaluate_heldout,
    load_heldout_bundle,
    write_heldout_reports,
)
from app.llm.providers import LLMStructuredResult, TokenUsage
from app.reliability.reporting import MeasurementSeries

HELDOUT = Path("evals/heldout")
STAGE58_DATASET = Path("evals/adaptive_graph.jsonl")


def _bundle():
    return load_heldout_bundle(
        HELDOUT / "cases.jsonl",
        HELDOUT / "labels.jsonl",
        HELDOUT / "claims.jsonl",
    )


class CapturingProvider:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.temperatures: list[float | None] = []

    def generate_structured(
        self, prompt: str, *, temperature: float | None = 0.0
    ) -> LLMStructuredResult:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        return LLMStructuredResult(
            text=json.dumps(self.response),
            usage=TokenUsage(prompt_tokens=10, completion_tokens=4),
            temperature=temperature,
        )


def test_heldout_dataset_is_separate_and_has_required_coverage() -> None:
    bundle = _bundle()
    stage58_ids = {case.case_id for case in load_dataset(STAGE58_DATASET)}
    assert len(bundle.cases) == 50
    assert len(bundle.claims) == 30
    assert not {case.case_id for case in bundle.cases}.intersection(stage58_ids)
    categories = {case.category for case in bundle.cases}
    assert {
        "local_only",
        "web_only",
        "academic_only",
        "local_web",
        "local_academic",
        "all_sources",
        "clarification",
        "insufficient_evidence",
        "conflicting_sources",
        "provider_partial_failure",
        "citation_mismatch",
        "duplicate_url",
        "low_quality_web",
        "stale_source",
        "snippet_body_mismatch",
        "similar_title_irrelevant",
        "academic_metadata_missing",
    }.issubset(categories)


def test_heldout_inputs_do_not_contain_golden_labels() -> None:
    forbidden = {
        "expected_intent",
        "expected_sources",
        "expected_route",
        "clarification_required",
        "expected_answer_mode",
        "expected_evidence_status",
        "label",
    }
    for line in (HELDOUT / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        assert forbidden.isdisjoint(json.loads(line))


def test_claim_annotation_schema_has_all_support_classes() -> None:
    labels = {claim.label for claim in _bundle().claims}
    assert labels == {
        "supported",
        "partially_supported",
        "unsupported",
        "contradicted",
        "common_knowledge",
        "reasoning_only",
    }


def test_human_labels_are_not_inserted_into_semantic_prompt() -> None:
    annotation = _bundle().claims[0]
    provider = CapturingProvider({"classification": "supported"})
    result = ClaimSemanticVerifier(provider).evaluate(annotation)
    assert result.classification == "supported"
    prompt = json.loads(provider.prompts[0])
    assert set(prompt) == {
        "task",
        "claim",
        "citation_id",
        "source_title",
        "source_url",
        "source_excerpt",
    }
    assert "label" not in prompt
    assert "support_strength" not in prompt
    assert "missing_citation" not in prompt
    assert "wrong_source" not in prompt


def test_query_temperature_benchmark_uses_inputs_not_golden_fields() -> None:
    bundle = _bundle()
    bundle.cases = bundle.cases[:1]
    bundle.labels = {bundle.cases[0].case_id: bundle.labels[bundle.cases[0].case_id]}
    provider = CapturingProvider(
        {
            "intent": "find_in_library",
            "complexity": "simple",
            "required_sources": ["local"],
            "freshness_required": False,
            "selected_books_relevant": True,
            "needs_clarification": False,
            "clarification_question": None,
            "answer_mode": "explanation",
            "subqueries": [],
            "confidence": 0.9,
        }
    )
    result = benchmark_query_temperatures(bundle, provider=provider, runs=2)
    assert result["temperature_zero"]["schema_valid_rate"] == 1
    assert result["production"]["route_accuracy"] == 1
    assert provider.temperatures == [0.0, 0.0, 0.0, 0.0]
    assert all("expected_route" not in prompt for prompt in provider.prompts)
    assert all("expected_sources" not in prompt for prompt in provider.prompts)


def test_confusion_metrics_calculate_precision_recall_and_error_rates() -> None:
    rows = [
        {"expected_problem": True, "prediction": True},
        {"expected_problem": True, "prediction": False},
        {"expected_problem": False, "prediction": True},
        {"expected_problem": False, "prediction": False},
    ]
    metrics = confusion_metrics(rows, prediction_key="prediction")
    assert metrics == {
        "evaluated": 4,
        "tp": 1,
        "fp": 1,
        "tn": 1,
        "fn": 1,
        "precision": 0.5,
        "recall": 0.5,
        "false_positive_rate": 0.5,
        "false_negative_rate": 0.5,
    }


def test_failed_measurements_do_not_enter_success_percentiles() -> None:
    series = MeasurementSeries()
    series.add_success(20)
    series.add_success(40)
    series.add_failure(TimeoutError())
    summary = series.summary()
    assert summary["p50"] == 30
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1


def test_heldout_report_is_reproducible_and_contains_no_input_text(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    first = evaluate_heldout(bundle, runs=2)
    second = evaluate_heldout(bundle, runs=2)
    assert (
        first["query_analysis"]["route_accuracy"]
        == second["query_analysis"]["route_accuracy"]
    )
    assert [row["request_id"] for row in first["case_runs"]] == [
        row["request_id"] for row in second["case_runs"]
    ]
    json_path = tmp_path / "heldout.json"
    markdown_path = tmp_path / "heldout.md"
    write_heldout_reports(first, json_path=json_path, markdown_path=markdown_path)
    serialized = json_path.read_text(encoding="utf-8")
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert bundle.cases[0].question not in serialized
    assert bundle.claims[0].claim not in serialized
    assert bundle.claims[0].source_excerpt not in serialized
    assert "Held-out Research Quality Evaluation" in markdown_path.read_text(
        encoding="utf-8"
    )
    assert first["production_recommendation"] == "collect more data before decision"


def test_failed_query_run_is_excluded_from_latency_percentiles(monkeypatch) -> None:
    bundle = _bundle()
    bundle.cases = bundle.cases[:2]
    bundle.labels = {case.case_id: bundle.labels[case.case_id] for case in bundle.cases}
    original = heldout_module.observe_analysis
    calls = 0

    def sometimes_fails(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected")
        return original(*args, **kwargs)

    monkeypatch.setattr(heldout_module, "observe_analysis", sometimes_fails)
    report = evaluate_heldout(bundle, runs=1)
    latency = report["query_analysis"]["latency_ms"]
    assert report["failures"]["count"] == 1
    assert latency["success_count"] == 1
    assert latency["failure_count"] == 1
    assert latency["p50"] is not None


def test_real_modes_are_disabled_by_default(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_heldout_research.py",
            "--real-query",
            "--confirm-costs",
            "--json-report",
            str(tmp_path / "report.json"),
            "--markdown-report",
            str(tmp_path / "report.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Real held-out evaluation is disabled" in result.stderr + result.stdout


def test_offline_runner_generates_reports_and_keeps_real_work_disabled(
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_heldout_research.py",
            "--runs",
            "1",
            "--json-report",
            str(json_path),
            "--markdown-report",
            str(markdown_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["dataset"]["case_count"] == 50
    assert report["real_query_temperature_comparison"]["executed"] is False
    assert report["real_mcp"]["executed"] is False


def test_evaluation_only_verifier_is_not_imported_by_production_graph() -> None:
    production_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("app/graphs").glob("*.py")
    )
    assert "app.evaluation" not in production_sources
    assert "ClaimSemanticVerifier" not in production_sources


def test_bundle_rejects_mismatched_case_and_label_ids(tmp_path: Path) -> None:
    cases = tmp_path / "cases.jsonl"
    labels = tmp_path / "labels.jsonl"
    claims = tmp_path / "claims.jsonl"
    cases.write_text(
        (HELDOUT / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    labels.write_text(
        (HELDOUT / "labels.jsonl").read_text(encoding="utf-8").splitlines()[1] + "\n",
        encoding="utf-8",
    )
    claims.write_text(
        (HELDOUT / "claims.jsonl").read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identical IDs"):
        load_heldout_bundle(cases, labels, claims)
