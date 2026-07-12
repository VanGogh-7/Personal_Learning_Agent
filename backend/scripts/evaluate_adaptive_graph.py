"""Evaluate the Stage 57 adaptive graph against human-authored golden labels.

Default execution is deterministic and offline. Real DeepSeek evaluation consumes
quota and requires PLA_REAL_PROVIDER_TESTS=true plus --real-providers and
--confirm-costs.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.evaluation.adaptive_graph import (
    ExperimentalLLMEvidenceGrader,
    ExperimentalSemanticVerifier,
    GraphVariant,
    evaluate_dataset,
    load_dataset,
    write_reports,
)
from app.llm.providers import get_llm_provider
from app.reliability.reporting import missing_real_provider_configuration

VARIANTS: tuple[GraphVariant, ...] = (
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
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND_ROOT / "evals" / "adaptive_graph.jsonl",
    )
    parser.add_argument("--variant", choices=VARIANTS, default="adaptive")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=57)
    parser.add_argument("--real-providers", action="store_true")
    parser.add_argument("--confirm-costs", action="store_true")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    parser.add_argument(
        "--grader",
        choices=["deterministic", "llm-experimental"],
        default="deterministic",
    )
    parser.add_argument(
        "--semantic-verifier",
        choices=["structural", "llm-experimental"],
        default="structural",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=Path("adaptive_graph_report.json"),
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=Path("adaptive_graph_report.md"),
    )
    parser.add_argument("--stdout-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be positive")
    settings = get_settings()
    provider = None
    provider_name = "deterministic"
    if args.real_providers:
        if not settings.pla_real_provider_tests or not args.confirm_costs:
            raise SystemExit(
                "Real evaluation is disabled. Set PLA_REAL_PROVIDER_TESTS=true "
                "and pass --real-providers --confirm-costs."
            )
        missing = missing_real_provider_configuration(settings, "deepseek")
        if missing:
            raise SystemExit(
                "Real DeepSeek evaluation skipped; missing: " + ", ".join(missing)
            )
        provider = get_llm_provider()
        provider_name = settings.deepseek_model
        print("WARNING: real QueryAnalysis evaluation consumes DeepSeek quota.")
    if (
        args.grader == "llm-experimental"
        or args.semantic_verifier == "llm-experimental"
    ) and provider is None:
        raise SystemExit(
            "Experimental LLM grader/verifier requires explicitly enabled real providers."
        )
    cases = load_dataset(args.dataset)
    report = evaluate_dataset(
        cases,
        variant=args.variant,
        runs=args.runs,
        seed=args.seed,
        provider=provider,
        provider_name=provider_name,
        input_cost_per_million=args.input_cost_per_million,
        output_cost_per_million=args.output_cost_per_million,
        grader_adapter=(
            ExperimentalLLMEvidenceGrader(provider)
            if provider is not None and args.grader == "llm-experimental"
            else None
        ),
        semantic_adapter=(
            ExperimentalSemanticVerifier(provider)
            if provider is not None and args.semantic_verifier == "llm-experimental"
            else None
        ),
        grader_name=args.grader,
        semantic_verifier_name=args.semantic_verifier,
    )
    write_reports(
        report,
        json_path=args.json_report,
        markdown_path=args.markdown_report,
    )
    if args.stdout_json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        query = report["query_analysis"]
        evidence = report["evidence_grading"]
        print(
            "Adaptive graph evaluation complete: "
            f"cases={report['dataset']['case_count']} runs={args.runs} "
            f"intent_accuracy={query['intent_accuracy']:.3f} "
            f"route_accuracy={query['route_accuracy']:.3f} "
            f"evidence_accuracy={evidence['accuracy']:.3f}"
        )
        print(f"JSON report: {args.json_report}")
        print(f"Markdown report: {args.markdown_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
