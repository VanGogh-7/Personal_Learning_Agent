"""Evaluate legacy-PDF retrieval variants against versioned offline fixtures."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.pdf_rag import (
    evaluate_pdf_retrieval,
    load_pdf_retrieval_dataset,
    write_pdf_retrieval_reports,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND_ROOT / "evals" / "legacy_pdf_retrieval.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json-report", type=Path, default=Path("pdf_rag_report.json"))
    parser.add_argument(
        "--markdown-report", type=Path, default=Path("pdf_rag_report.md")
    )
    parser.add_argument("--stdout-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = load_pdf_retrieval_dataset(args.dataset)
    report = evaluate_pdf_retrieval(cases, top_k=args.top_k)
    write_pdf_retrieval_reports(
        report, json_path=args.json_report, markdown_path=args.markdown_report
    )
    if args.stdout_json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        variants = report["variants"]
        print(
            f"PDF RAG evaluation complete: cases={len(cases)} "
            f"dense_recall={variants['dense'][f'recall_at_{args.top_k}']:.3f} "
            f"hybrid_recall={variants['hybrid'][f'recall_at_{args.top_k}']:.3f} "
            f"dual_recall={variants['dual'][f'recall_at_{args.top_k}']:.3f}"
        )
        print("Fixture benchmark: no external OCR or real visual model executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
