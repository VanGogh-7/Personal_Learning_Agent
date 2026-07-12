import json
import subprocess
import sys
from pathlib import Path

import pytest

import app.evaluation.adaptive_graph as evaluation_module
from app.evaluation.adaptive_graph import (
    AdaptiveEvaluationCase,
    evaluate_dataset,
    load_dataset,
    render_markdown,
    write_reports,
)
from app.reliability.reporting import MeasurementSeries

DATASET = Path("evals/adaptive_graph.jsonl")


def test_versioned_dataset_has_required_coverage_and_valid_schema() -> None:
    cases = load_dataset(DATASET)
    assert 50 <= len(cases) <= 100
    categories = {case.category for case in cases}
    assert {
        "local_library",
        "stable_concept",
        "proof",
        "clarification",
        "current_information",
        "academic",
        "local_academic",
        "all_sources",
        "evidence_empty",
        "evidence_insufficient",
        "evidence_conflicting",
        "provider_partial_failure",
        "citation_missing",
        "citation_hallucinated",
    }.issubset(categories)


def test_dataset_rejects_duplicate_and_invalid_cases(tmp_path: Path) -> None:
    valid = AdaptiveEvaluationCase(
        case_id="one",
        category="test",
        question="Hello",
        expected_intent="follow_up",
        expected_sources=[],
        expected_route="direct_answer",
        expected_answer_mode="concise",
    ).model_dump_json()
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(f"{valid}\n{valid}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_dataset(duplicate)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"case_id":"broken"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_dataset(invalid)


def test_deterministic_evaluation_is_reproducible_and_reports_metrics() -> None:
    cases = load_dataset(DATASET)
    first = evaluate_dataset(cases, variant="adaptive", runs=2, seed=57)
    second = evaluate_dataset(cases, variant="adaptive", runs=2, seed=57)
    assert (
        first["query_analysis"]["intent_accuracy"]
        == second["query_analysis"]["intent_accuracy"]
    )
    assert first["query_analysis"]["route_accuracy"] == 1.0
    assert first["query_analysis"]["repeated_run_stability"] == 1.0
    assert first["evidence_grading"]["accuracy"] == 1.0
    assert first["citations"]["classification_accuracy"] == 1.0
    assert [row["request_id"] for row in first["case_runs"]] == [
        row["request_id"] for row in second["case_runs"]
    ]


def test_failed_case_is_excluded_from_success_percentiles(monkeypatch) -> None:
    cases = load_dataset(DATASET)[:2]
    original = evaluation_module.observe_analysis
    calls = 0

    def sometimes_fails(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected")
        return original(*args, **kwargs)

    monkeypatch.setattr(evaluation_module, "observe_analysis", sometimes_fails)
    report = evaluate_dataset(cases, variant="adaptive", runs=1, seed=1)
    latency = report["query_analysis"]["latency_ms"]
    assert report["failures"]["count"] == 1
    assert latency["success_count"] == 1
    assert latency["failure_count"] == 1
    assert latency["p50"] is not None


def test_percentile_calculation_and_failure_exclusion() -> None:
    series = MeasurementSeries()
    series.add_success(10)
    series.add_success(20)
    series.add_failure(TimeoutError())
    summary = series.summary()
    assert summary["p50"] == 15
    assert summary["p95"] == 19.5
    assert summary["failure_count"] == 1


def test_json_and_markdown_reports_are_generated_without_sensitive_content(
    tmp_path: Path,
) -> None:
    report = evaluate_dataset(
        load_dataset(DATASET), variant="adaptive", runs=1, seed=57
    )
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    write_reports(report, json_path=json_path, markdown_path=markdown_path)
    serialized = json_path.read_text(encoding="utf-8")
    assert json.loads(serialized)["dataset"]["case_count"] >= 50
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "What does this book" not in serialized
    assert "# Adaptive Graph Evaluation" in markdown_path.read_text(encoding="utf-8")
    assert render_markdown(report).endswith(
        "Semantic support is not inferred by the structural verifier."
    )


def test_graph_variants_produce_comparable_route_metrics() -> None:
    cases = load_dataset(DATASET)
    adaptive = evaluate_dataset(cases, variant="adaptive", runs=1, seed=57)
    direct = evaluate_dataset(cases, variant="direct_answer", runs=1, seed=57)
    single = evaluate_dataset(cases, variant="single_source_adaptive", runs=1, seed=57)
    assert adaptive["query_analysis"]["route_accuracy"] == 1.0
    assert direct["query_analysis"]["route_accuracy"] < 0.2
    assert single["query_analysis"]["route_accuracy"] < 1.0
    assert adaptive["graph_variant"]["latency_proxy_ms"]["p95"] is not None


def test_real_provider_and_experimental_judges_are_disabled_by_default(
    tmp_path: Path,
) -> None:
    command = [
        sys.executable,
        "scripts/evaluate_adaptive_graph.py",
        "--dataset",
        str(DATASET),
        "--real-providers",
        "--json-report",
        str(tmp_path / "report.json"),
        "--markdown-report",
        str(tmp_path / "report.md"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "Real evaluation is disabled" in result.stderr + result.stdout

    experimental = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_adaptive_graph.py",
            "--dataset",
            str(DATASET),
            "--grader",
            "llm-experimental",
            "--json-report",
            str(tmp_path / "experiment.json"),
            "--markdown-report",
            str(tmp_path / "experiment.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert experimental.returncode != 0
    assert "requires explicitly enabled real providers" in (
        experimental.stderr + experimental.stdout
    )
