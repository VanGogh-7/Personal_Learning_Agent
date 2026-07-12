from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.pdf_rag import (
    evaluate_pdf_retrieval,
    load_pdf_retrieval_dataset,
    write_pdf_retrieval_reports,
)
from scripts.evaluate_pdf_rag import main

DATASET = Path(__file__).resolve().parents[1] / "evals" / "legacy_pdf_retrieval.jsonl"


def test_versioned_dataset_covers_required_pdf_and_query_categories() -> None:
    cases = load_pdf_retrieval_dataset(DATASET)

    assert {case.pdf_type for case in cases} == {"born_digital", "scanned", "mixed"}
    assert {
        "formula",
        "theorem",
        "proof",
        "figure",
        "table",
        "ocr_error",
        "exact_section",
    } <= {case.query_kind for case in cases}


def test_evaluation_calculates_metrics_and_failure_exclusion() -> None:
    report = evaluate_pdf_retrieval(load_pdf_retrieval_dataset(DATASET), top_k=3)
    variants = report["variants"]

    assert variants["hybrid"]["recall_at_3"] > variants["dense"]["recall_at_3"]
    assert variants["visual"]["failure_count"] == 1
    assert variants["visual"]["success_count"] + 1 == report["dataset"]["case_count"]
    assert (
        variants["dual"]["citation_page_accuracy"]
        >= variants["hybrid"]["citation_page_accuracy"]
    )
    assert report["dataset"]["real_visual_model_executed"] is False


def test_report_generation_is_deterministic_and_marks_fixture_scope(tmp_path) -> None:
    report = evaluate_pdf_retrieval(load_pdf_retrieval_dataset(DATASET))
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_pdf_retrieval_reports(
        report, json_path=json_path, markdown_path=markdown_path
    )

    assert json.loads(json_path.read_text()) == report
    assert "Offline fixture benchmark only" in markdown_path.read_text()
    assert "real visual model" in markdown_path.read_text()


def test_invalid_dataset_is_rejected(tmp_path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text('{"case_id":"missing"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        load_pdf_retrieval_dataset(path)


def test_evaluation_cli_smoke(tmp_path) -> None:
    json_path = tmp_path / "cli.json"
    markdown_path = tmp_path / "cli.md"

    assert (
        main(
            [
                "--dataset",
                str(DATASET),
                "--json-report",
                str(json_path),
                "--markdown-report",
                str(markdown_path),
            ]
        )
        == 0
    )
    assert json_path.exists()
    assert markdown_path.exists()
