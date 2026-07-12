from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation.stage62 import (
    REQUIRED_DOCUMENT_FEATURES,
    REQUIRED_QUERY_KINDS,
    RetrievalRun,
    build_dual_runs,
    evaluate_real_retrieval,
    load_scanned_math_dataset,
    probe_environment,
    reciprocal_rank_fusion,
)


def _write_dataset(root: Path, *, sealed: bool = True) -> None:
    books = []
    features = sorted(REQUIRED_DOCUMENT_FEATURES)
    for index in range(3):
        payload = f"fixture-pdf-{index}".encode()
        path = root / "books" / f"book-{index}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        books.append(
            {
                "book_id": f"book_{index}",
                "title": f"Book {index}",
                "pdf_file": f"books/book-{index}.pdf",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "split": "development" if index == 0 else "held_out",
                "document_features": features,
                "source_and_permission_notes": "Test-owned synthetic bytes.",
            }
        )
    manifest = {
        "dataset_id": "stage62-test",
        "version": "1",
        "annotation_status": "sealed" if sealed else "draft",
        "tuning_prohibited_on_held_out": True,
        "books": books,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    kinds = sorted(REQUIRED_QUERY_KINDS)
    lines = []
    for index in range(50):
        book_index = 0 if index < 10 else 1 + index % 2
        split = "development" if book_index == 0 else "held_out"
        lines.append(
            json.dumps(
                {
                    "query_id": f"query_{index}",
                    "book_id": f"book_{book_index}",
                    "query": f"Human query {index}",
                    "query_kind": kinds[index % len(kinds)],
                    "relevant_pages": [3, 4],
                    "relevant_regions": [{"page": 3, "bbox": [10, 20, 30, 40]}],
                    "expected_section": "Section 2",
                    "citation_page": 3,
                    "ocr_difficulty": "high" if index % 2 else "medium",
                    "visual_layout_dependency": bool(index % 2),
                    "split": split,
                }
            )
        )
    (root / "queries.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


def test_dataset_enforces_real_annotation_contract(tmp_path: Path) -> None:
    _write_dataset(tmp_path)

    manifest, queries = load_scanned_math_dataset(tmp_path)

    assert len(manifest.books) == 3
    assert len(queries) == 50
    assert {query.split for query in queries} == {"development", "held_out"}


def test_draft_dataset_cannot_be_reported_as_real(tmp_path: Path) -> None:
    _write_dataset(tmp_path, sealed=False)

    with pytest.raises(ValueError, match="sealed human-labelled"):
        load_scanned_math_dataset(tmp_path)


def test_rank_fusion_uses_rank_and_deterministic_ties() -> None:
    assert reciprocal_rank_fusion([8, 3, 5], [5, 3, 9]) == [5, 3, 8, 9]


def test_dual_observations_use_rank_fusion_and_add_costs() -> None:
    text = RetrievalRun(
        run_id="text-1",
        query_id="q1",
        variant="parent_context",
        ranked_pages=[8, 3, 5],
        query_ms=10,
        indexing_ms=100,
        storage_bytes=1000,
    )
    visual = RetrievalRun(
        run_id="visual-1",
        query_id="q1",
        variant="visual",
        ranked_pages=[5, 3, 9],
        query_ms=70,
        indexing_ms=600,
        storage_bytes=6500,
    )

    dual = build_dual_runs([text], [visual])[0]

    assert dual.ranked_pages == [5, 3, 8, 9]
    assert dual.query_ms >= 80
    assert dual.storage_bytes == 7500
    assert dual.fusion_ms is not None


def test_real_metrics_cover_all_cutoffs_and_keep_visual_experimental(
    tmp_path: Path,
) -> None:
    _write_dataset(tmp_path)
    manifest, queries = load_scanned_math_dataset(tmp_path)
    held_out = [query for query in queries if query.split == "held_out"]
    runs = []
    for variant in ("parent_context", "visual", "dual"):
        for query in held_out:
            runs.append(
                RetrievalRun(
                    run_id="only-one-run",
                    query_id=query.query_id,
                    variant=variant,
                    ranked_pages=[3, 8, 4],
                    query_ms=10 if variant == "parent_context" else 70,
                    indexing_ms=100,
                    storage_bytes=1000,
                )
            )

    report = evaluate_real_retrieval(
        manifest, queries, runs, environment={"fixture": True}
    )

    assert report["variants"]["dual"]["recall_at_1"] == 0.5
    assert report["variants"]["dual"]["recall_at_5"] == 1
    assert report["variants"]["dual"]["citation_page_accuracy"] == 1
    assert "visual_experimental" in report["production_decision"]
    assert "not complete BM25" in report["terminology"]["postgres_fts"]


def test_environment_probe_never_installs_or_downloads() -> None:
    environment = probe_environment()

    assert "pymupdf" in environment
    assert "tesseract" in environment
    assert "colpali_engine_installed" in environment
