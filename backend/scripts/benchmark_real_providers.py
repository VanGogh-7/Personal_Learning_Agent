"""Opt-in benchmarks for real DeepSeek, Zhipu, and Tavily services.

This command consumes Provider quota. It refuses to run unless both
``PLA_REAL_PROVIDER_TESTS=true`` and ``--confirm-costs`` are supplied.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.web_research import get_web_research_provider
from app.core.config import get_settings
from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.providers import get_embedding_provider
from app.llm.providers import get_llm_provider
from app.providers.http_clients import provider_http_clients
from app.reliability.reporting import (
    MeasurementSeries,
    missing_real_provider_configuration,
    safe_environment_report,
    validate_embedding_dimension,
)

SHORT_PROMPT = "Answer in one sentence: what is a Banach space?"
MEDIUM_MATH_PROMPT = """Explain the closed graph theorem concisely.
Use Markdown headings, inline LaTeX such as $T: X \\to Y$, one display equation,
and a short structured proof outline. Do not exceed 700 words.
"""
LONG_PROMPT = """Write a detailed but bounded tutorial on Banach spaces and the
closed graph theorem. Use Markdown sections, inline and display LaTeX, one code
block containing a harmless pseudocode example, and a final summary. Stay within
the supplied token budget and finish the response normally.
"""
EMBEDDING_TEXT = "A Banach space is a complete normed vector space."
TAVILY_QUERY = "latest stable Python release and official release date"


@dataclass(frozen=True)
class DeepSeekRun:
    first_token_ms: float
    generation_ms: float
    total_ms: float
    output_characters: int
    completion_tokens: int | None
    tokens_per_second: float | None
    finish_reason: str | None


def new_metric_map(*names: str) -> dict[str, MeasurementSeries]:
    return {name: MeasurementSeries() for name in names}


async def measure_deepseek(prompt: str, *, max_tokens: int) -> DeepSeekRun:
    provider = get_llm_provider()
    started_at = time.perf_counter()
    first_at: float | None = None
    last_at: float | None = None
    output_characters = 0
    completion_tokens: int | None = None
    finish_reason: str | None = None
    async for chunk in provider.stream_chat_completion(prompt, max_tokens=max_tokens):
        if chunk.delta:
            now = time.perf_counter()
            first_at = first_at or now
            last_at = now
            output_characters += len(chunk.delta)
        if chunk.finish_reason is not None:
            finish_reason = chunk.finish_reason
        if chunk.usage is not None:
            completion_tokens = chunk.usage.completion_tokens
    ended_at = time.perf_counter()
    if first_at is None or last_at is None:
        raise RuntimeError("DeepSeek returned no visible stream content")
    generation_seconds = max(0.0, last_at - first_at)
    tokens_per_second = (
        completion_tokens / generation_seconds
        if completion_tokens is not None and generation_seconds > 0
        else None
    )
    return DeepSeekRun(
        first_token_ms=(first_at - started_at) * 1000,
        generation_ms=generation_seconds * 1000,
        total_ms=(ended_at - started_at) * 1000,
        output_characters=output_characters,
        completion_tokens=completion_tokens,
        tokens_per_second=tokens_per_second,
        finish_reason=finish_reason,
    )


async def cancel_deepseek_after_first_token() -> float:
    provider = get_llm_provider()
    stream = provider.stream_chat_completion(LONG_PROMPT, max_tokens=512)
    async for chunk in stream:
        if not chunk.delta:
            continue
        started_at = time.perf_counter()
        await stream.aclose()
        return (time.perf_counter() - started_at) * 1000
    raise RuntimeError("DeepSeek cancellation probe received no token")


async def benchmark_deepseek(
    runs: int, warmups: int, long_tokens: int
) -> dict[str, Any]:
    scenarios = {
        "short": (SHORT_PROMPT, 128),
        "medium_math": (MEDIUM_MATH_PROMPT, 900),
        "long": (LONG_PROMPT, long_tokens),
    }
    output: dict[str, Any] = {}
    for name, (prompt, max_tokens) in scenarios.items():
        metrics = new_metric_map(
            "first_token_ms",
            "generation_ms",
            "total_ms",
            "output_characters",
            "completion_tokens",
            "tokens_per_second",
        )
        finish_reasons: dict[str, int] = {}
        for _ in range(warmups):
            try:
                await measure_deepseek(prompt, max_tokens=max_tokens)
            except Exception:
                pass
        for _ in range(runs):
            try:
                measured = await measure_deepseek(prompt, max_tokens=max_tokens)
                metrics["first_token_ms"].add_success(measured.first_token_ms)
                metrics["generation_ms"].add_success(measured.generation_ms)
                metrics["total_ms"].add_success(measured.total_ms)
                metrics["output_characters"].add_success(measured.output_characters)
                if measured.completion_tokens is not None:
                    metrics["completion_tokens"].add_success(measured.completion_tokens)
                if measured.tokens_per_second is not None:
                    metrics["tokens_per_second"].add_success(measured.tokens_per_second)
                reason = measured.finish_reason or "missing"
                finish_reasons[reason] = finish_reasons.get(reason, 0) + 1
            except Exception as exc:
                for series in metrics.values():
                    series.add_failure(exc)
        output[name] = {
            "runs": runs,
            "finish_reasons": finish_reasons,
            "metrics": {key: value.summary() for key, value in metrics.items()},
        }
    cancellation = MeasurementSeries()
    try:
        cancellation.add_success(await cancel_deepseek_after_first_token())
    except Exception as exc:
        cancellation.add_failure(exc)
    output["cancellation_after_first_token_ms"] = cancellation.summary()
    return output


def benchmark_zhipu(runs: int, warmups: int) -> dict[str, Any]:
    provider = get_embedding_provider()
    latency = MeasurementSeries()
    actual_dimensions: list[int] = []
    for _ in range(warmups):
        provider.embed_text(EMBEDDING_TEXT)
    for _ in range(runs):
        started_at = time.perf_counter()
        try:
            embedding = provider.embed_text(EMBEDDING_TEXT)
            elapsed = (time.perf_counter() - started_at) * 1000
            actual = len(embedding)
            validate_embedding_dimension(
                actual=actual,
                configured=provider.dimension,
                schema=EMBEDDING_DIMENSION,
            )
            actual_dimensions.append(actual)
            latency.add_success(elapsed)
        except Exception as exc:
            latency.add_failure(exc)
    first_client = provider_http_clients.get("embedding")
    second_client = provider_http_clients.get("embedding")
    return {
        "runs": runs,
        "transport": "synchronous_reused_httpx_client",
        "transport_cancellation_supported": False,
        "latency_ms": latency.summary(),
        "actual_dimensions": sorted(set(actual_dimensions)),
        "configured_dimension": provider.dimension,
        "schema_dimension": EMBEDDING_DIMENSION,
        "client_reused": first_client is second_client,
    }


def benchmark_tavily(runs: int, warmups: int) -> dict[str, Any]:
    provider = get_web_research_provider()
    latency = MeasurementSeries()
    result_counts: list[int] = []
    normalized_bytes: list[int] = []
    for _ in range(warmups):
        provider.research(TAVILY_QUERY)
    for _ in range(runs):
        started_at = time.perf_counter()
        try:
            result = provider.research(TAVILY_QUERY)
            elapsed = (time.perf_counter() - started_at) * 1000
            if result.status != "available":
                raise RuntimeError("Tavily result unavailable")
            latency.add_success(elapsed)
            result_counts.append(len(result.sources))
            normalized_bytes.append(
                len(
                    json.dumps(
                        [
                            {
                                "title": source.title,
                                "url": source.url,
                                "excerpt": source.excerpt,
                            }
                            for source in result.sources
                        ],
                        ensure_ascii=False,
                    ).encode("utf-8")
                )
            )
        except Exception as exc:
            latency.add_failure(exc)
    first_client = provider_http_clients.get("web")
    second_client = provider_http_clients.get("web")
    return {
        "runs": runs,
        "latency_ms": latency.summary(),
        "result_count": _numeric_summary(result_counts),
        "normalized_response_bytes": _numeric_summary(normalized_bytes),
        "client_reused": first_client is second_client,
    }


def _numeric_summary(values: list[int]) -> dict[str, float | int | None]:
    series = MeasurementSeries(values=[float(value) for value in values])
    summary = series.summary()
    return {
        key: summary[key]
        for key in ("count", "min", "max", "mean", "p50", "p90", "p95")
    }


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs", type=int, default=settings.pla_real_provider_benchmark_runs
    )
    parser.add_argument(
        "--warmups", type=int, default=settings.pla_real_provider_warmup_runs
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["deepseek", "zhipu", "tavily"],
        help="Provider to benchmark; defaults to all three.",
    )
    parser.add_argument("--confirm-costs", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


async def run_benchmarks(
    args: argparse.Namespace, settings: Any, providers: list[str]
) -> int:
    report: dict[str, Any] = {
        "environment": safe_environment_report(settings),
        "runs": args.runs,
        "warmup_runs": args.warmups,
        "quota_warning": "This benchmark consumed real Provider quota.",
        "results": {},
    }
    try:
        if "deepseek" in providers:
            report["results"]["deepseek"] = await benchmark_deepseek(
                args.runs, args.warmups, settings.pla_long_answer_max_tokens
            )
        if "zhipu" in providers:
            report["results"]["zhipu"] = benchmark_zhipu(args.runs, args.warmups)
        if "tavily" in providers:
            report["results"]["tavily"] = benchmark_tavily(args.runs, args.warmups)
        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        else:
            print("Real Provider benchmark report")
            print(
                f"Runs={args.runs}; warmups={args.warmups}; "
                f"tested_at={report['environment']['tested_at_utc']}"
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await provider_http_clients.aclose()
        provider_http_clients.close()
    return 0


def main() -> int:
    args = parse_args()
    settings = get_settings()
    if not settings.pla_real_provider_tests or not args.confirm_costs:
        raise SystemExit(
            "Real benchmarks are disabled. Set PLA_REAL_PROVIDER_TESTS=true and "
            "pass --confirm-costs to consume Provider quota."
        )
    providers = args.provider or ["deepseek", "zhipu", "tavily"]
    missing = {
        provider: missing_real_provider_configuration(settings, provider)
        for provider in providers
    }
    missing = {key: value for key, value in missing.items() if value}
    if missing:
        details = "; ".join(
            f"{provider}: {', '.join(values)}" for provider, values in missing.items()
        )
        raise SystemExit(f"Missing real Provider configuration: {details}")
    return asyncio.run(run_benchmarks(args, settings, providers))


if __name__ == "__main__":
    raise SystemExit(main())
