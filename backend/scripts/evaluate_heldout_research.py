"""Run the isolated Stage 59 held-out research and claim-support evaluation."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.evaluation.heldout import (
    HeldOutBundle,
    benchmark_query_temperatures,
    evaluate_heldout,
    load_heldout_bundle,
    write_heldout_reports,
)
from app.llm.providers import get_llm_provider
from app.mcp.client import mcp_client_manager
from app.mcp.gateway import MCPToolGateway
from app.mcp.research import run_mcp_academic_research, run_mcp_web_research
from app.observability.latency import AgentLatencyTrace, latency_trace_context
from app.reliability.reporting import (
    MeasurementSeries,
    missing_real_provider_configuration,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    heldout = BACKEND_ROOT / "evals" / "heldout"
    parser.add_argument("--cases", type=Path, default=heldout / "cases.jsonl")
    parser.add_argument("--labels", type=Path, default=heldout / "labels.jsonl")
    parser.add_argument("--claims", type=Path, default=heldout / "claims.jsonl")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--real-query-max-cases", type=int, default=12)
    parser.add_argument("--real-query", action="store_true")
    parser.add_argument("--real-mcp", action="store_true")
    parser.add_argument("--semantic-verifier", action="store_true")
    parser.add_argument("--confirm-costs", action="store_true")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    parser.add_argument("--json-report", type=Path, default=Path("heldout_report.json"))
    parser.add_argument(
        "--markdown-report", type=Path, default=Path("heldout_report.md")
    )
    return parser.parse_args(argv)


async def collect_real_mcp(bundle, *, max_cases: int = 8) -> dict[str, Any]:
    latency = MeasurementSeries()
    failures: list[str] = []
    samples: list[dict[str, Any]] = []
    fallback_count = 0
    raw_count = 0
    normalized_keys: set[str] = set()
    selected = [
        case
        for case in bundle.cases
        if case.category
        in {"web_only", "academic_only", "all_sources", "provider_partial_failure"}
    ][:max_cases]
    await mcp_client_manager.startup()
    try:
        for case in selected:
            label = bundle.labels[case.case_id]
            gateway = MCPToolGateway()
            trace = AgentLatencyTrace(request_id=f"heldout-{case.case_id}")
            started = perf_counter()
            try:
                with latency_trace_context(trace):
                    if "academic" in label.expected_sources:
                        result = await run_mcp_academic_research(
                            case.question, gateway=gateway
                        )
                    else:
                        result = await run_mcp_web_research(
                            case.question, gateway=gateway
                        )
                latency.add_success((perf_counter() - started) * 1_000)
                fallback_count += int(trace.counters.get("mcp_fallback_count") or 0)
                raw_count += len(result.sources)
                for source in result.sources:
                    key = (source.url or source.evidence_id or source.title).lower()
                    normalized_keys.add(key)
                    samples.append(
                        {
                            "case_id": case.case_id,
                            "provider": source.provider,
                            "source_type": source.source_type,
                            "title": source.title[:300],
                            "url": source.url,
                            "excerpt": source.excerpt[:300],
                            "doi": source.doi,
                            "arxiv_id": source.arxiv_id,
                            "human_annotation": "pending",
                        }
                    )
            except Exception as exc:
                latency.add_failure(exc)
                failures.append(type(exc).__name__)
    finally:
        await mcp_client_manager.shutdown()
    valid = len(samples)
    return {
        "executed": True,
        "case_count": len(selected),
        "success_rate": latency.summary()["success_count"] / len(selected)
        if selected
        else None,
        "fallback_count": fallback_count,
        "normalized_evidence_count": valid,
        "deduplication_rate": 1 - len(normalized_keys) / raw_count
        if raw_count
        else None,
        "latency_ms": latency.summary(),
        "cost_per_valid_evidence": None,
        "failure_types": sorted(set(failures)),
        "samples": samples,
        "note": "Dynamic normalized samples require human quality annotation.",
    }


def select_stratified_cases(bundle: HeldOutBundle, limit: int) -> HeldOutBundle:
    """Select a bounded category-balanced subset without looking at labels."""
    if limit < 1:
        raise ValueError("real query case limit must be positive")
    selected = []
    seen_categories: set[str] = set()
    for case in bundle.cases:
        if case.category not in seen_categories:
            selected.append(case)
            seen_categories.add(case.category)
            if len(selected) == limit:
                break
    if len(selected) < limit:
        selected_ids = {case.case_id for case in selected}
        selected.extend(
            case for case in bundle.cases if case.case_id not in selected_ids
        )
    selected = selected[:limit]
    return HeldOutBundle(
        cases=selected,
        labels={case.case_id: bundle.labels[case.case_id] for case in selected},
        claims=[],
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.runs < 1:
        raise SystemExit("--runs must be positive")
    if args.real_query_max_cases < 1:
        raise SystemExit("--real-query-max-cases must be positive")
    settings = get_settings()
    wants_real = args.real_query or args.real_mcp or args.semantic_verifier
    if wants_real and (not settings.pla_real_provider_tests or not args.confirm_costs):
        raise SystemExit(
            "Real held-out evaluation is disabled. Set PLA_REAL_PROVIDER_TESTS=true "
            "and pass --confirm-costs with explicit real flags."
        )
    provider = None
    if args.real_query or args.semantic_verifier:
        missing = missing_real_provider_configuration(settings, "deepseek")
        if missing:
            raise SystemExit(
                "Real DeepSeek held-out evaluation skipped; missing: "
                + ", ".join(missing)
            )
        provider = get_llm_provider()
    if args.real_mcp and (not settings.mcp_enabled or not settings.mcp_real_tests):
        raise SystemExit(
            "Real MCP held-out evaluation skipped; MCP_ENABLED and MCP_REAL_TESTS "
            "must both be true."
        )
    bundle = load_heldout_bundle(args.cases, args.labels, args.claims)
    report = evaluate_heldout(
        bundle,
        runs=args.runs,
        provider=None,
        provider_name="deterministic",
        semantic_provider=provider if args.semantic_verifier else None,
        input_cost_per_million=args.input_cost_per_million,
        output_cost_per_million=args.output_cost_per_million,
    )
    real_query_report = (
        benchmark_query_temperatures(
            select_stratified_cases(bundle, args.real_query_max_cases),
            provider=provider,
            runs=args.runs,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
        )
        if args.real_query and provider is not None
        else {"executed": False, "reason": "Real DeepSeek evaluation not enabled."}
    )
    if args.real_query:
        real_query_report["executed"] = True
        real_query_report["model"] = settings.deepseek_model
    report["real_query_temperature_comparison"] = real_query_report
    report["configuration"]["semantic_provider"] = (
        settings.deepseek_model if args.semantic_verifier else None
    )
    report["real_mcp"] = (
        asyncio.run(collect_real_mcp(bundle))
        if args.real_mcp
        else {"executed": False, "reason": "Real MCP evaluation not enabled."}
    )
    report["run_metadata"] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": "local backend process over configured public network",
        "real_query_enabled": args.real_query,
        "real_mcp_enabled": args.real_mcp,
        "semantic_verifier_enabled": args.semantic_verifier,
    }
    write_heldout_reports(
        report, json_path=args.json_report, markdown_path=args.markdown_report
    )
    print(
        "Held-out evaluation complete: "
        f"cases={report['dataset']['case_count']} "
        f"claims={report['dataset']['claim_count']} "
        f"route_accuracy={report['query_analysis']['route_accuracy']:.3f} "
        f"grader_accuracy={report['deterministic_grader']['accuracy']:.3f}"
    )
    print(f"Decision: {report['production_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
