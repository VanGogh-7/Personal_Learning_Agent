from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.evaluation.stage62 import benchmark_external_ocr, load_scanned_math_dataset


@pytest.mark.external_ocr
def test_real_scanned_math_ocr() -> None:
    dataset = os.getenv("PLA_STAGE62_DATASET_DIR")
    if os.getenv("PLA_EXTERNAL_OCR_TESTS") != "true" or not dataset:
        pytest.skip("requires PLA_EXTERNAL_OCR_TESTS=true and PLA_STAGE62_DATASET_DIR")
    root = Path(dataset)
    manifest, _ = load_scanned_math_dataset(root)

    report = benchmark_external_ocr(root, manifest)

    if report["status"] == "skipped":
        pytest.skip(str(report["reason"]))
    assert report["real_external_ocr"] is True
    assert report["page_count"] > 0


@pytest.mark.visual_gpu
def test_real_colqwen2_visual_retrieval() -> None:
    dataset = os.getenv("PLA_STAGE62_DATASET_DIR")
    model_path = os.getenv("PLA_COLQWEN2_MODEL_PATH")
    if os.getenv("PLA_VISUAL_GPU_TESTS") != "true" or not dataset or not model_path:
        pytest.skip(
            "requires PLA_VISUAL_GPU_TESTS=true, PLA_STAGE62_DATASET_DIR, "
            "and PLA_COLQWEN2_MODEL_PATH"
        )
    from app.evaluation.colqwen import run_colqwen2_experiment

    root = Path(dataset)
    manifest, queries = load_scanned_math_dataset(root)
    runs, environment = run_colqwen2_experiment(
        root, manifest, queries, local_model_path=Path(model_path)
    )

    assert runs
    assert environment["model_family"] == "colqwen2"
    assert environment["ann_index"] is False
