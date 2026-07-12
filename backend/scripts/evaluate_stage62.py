"""Validate and score explicit Stage 62 real OCR and retrieval experiments."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.stage62 import (
    benchmark_external_ocr,
    evaluate_real_retrieval,
    load_retrieval_runs,
    load_scanned_math_dataset,
    probe_environment,
    write_json_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--json-report", type=Path, default=Path("stage62-report.json"))
    parser.add_argument("--probe-environment", action="store_true")
    parser.add_argument("--run-ocr", action="store_true")
    parser.add_argument("--run-visual", action="store_true")
    parser.add_argument("--local-colqwen2-model", type=Path)
    parser.add_argument("--visual-observations", type=Path)
    parser.add_argument("--render-dpi", type=int, default=144)
    parser.add_argument("--confirm-external-tools", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.probe_environment and args.dataset_dir is None:
        report = {"stage": 62, "environment": probe_environment()}
        write_json_report(report, args.json_report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.dataset_dir is None:
        raise SystemExit(
            "--dataset-dir is required unless only probing the environment"
        )
    manifest, queries = load_scanned_math_dataset(args.dataset_dir)
    report: dict[str, object] = {
        "stage": 62,
        "dataset": {"dataset_id": manifest.dataset_id, "query_count": len(queries)},
        "environment": probe_environment(),
    }
    if args.run_ocr:
        enabled = os.getenv("PLA_EXTERNAL_OCR_TESTS") == "true"
        if not enabled or not args.confirm_external_tools:
            report["ocr"] = {
                "status": "skipped",
                "reason": "requires PLA_EXTERNAL_OCR_TESTS=true and --confirm-external-tools",
            }
        else:
            report["ocr"] = benchmark_external_ocr(args.dataset_dir, manifest)
    if args.run_visual:
        enabled = os.getenv("PLA_VISUAL_GPU_TESTS") == "true"
        if (
            not enabled
            or not args.confirm_external_tools
            or args.local_colqwen2_model is None
        ):
            report["visual"] = {
                "status": "skipped",
                "reason": (
                    "requires PLA_VISUAL_GPU_TESTS=true, --confirm-external-tools, "
                    "and --local-colqwen2-model"
                ),
                "real_visual_model_executed": False,
            }
        else:
            from app.evaluation.colqwen import (
                run_colqwen2_experiment,
                write_retrieval_runs,
            )

            try:
                visual_runs, visual_environment = run_colqwen2_experiment(
                    args.dataset_dir,
                    manifest,
                    queries,
                    local_model_path=args.local_colqwen2_model,
                    dpi=args.render_dpi,
                )
            except RuntimeError as exc:
                report["visual"] = {
                    "status": "skipped",
                    "reason": str(exc),
                    "real_visual_model_executed": False,
                }
            else:
                output = args.visual_observations or Path(
                    "stage62-visual-observations.jsonl"
                )
                write_retrieval_runs(visual_runs, output)
                report["visual"] = {
                    "status": "executed",
                    "real_visual_model_executed": True,
                    "model": "ColQwen2",
                    "environment": visual_environment,
                    "observation_file": str(output),
                }
    if args.observations:
        report["retrieval"] = evaluate_real_retrieval(
            manifest,
            queries,
            load_retrieval_runs(args.observations),
            environment=probe_environment(),
        )
    write_json_report(report, args.json_report)
    print(f"Stage 62 report written to {args.json_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
