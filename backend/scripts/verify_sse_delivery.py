"""Verify incremental PLA SSE delivery through a direct or proxy base URL."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.reliability.reporting import MeasurementSeries
from app.reliability.sse_probe import probe_sse_delivery


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=settings.pla_sse_target_url)
    parser.add_argument(
        "--route",
        choices=["direct", "local_only", "web_only", "both"],
        default="local_only",
    )
    parser.add_argument("--conversation-id")
    parser.add_argument("--library-item-id", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--cancel-after-first-token", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


async def run_probes(args: argparse.Namespace) -> list[dict[str, object]]:
    timeout = httpx.Timeout(
        connect=min(10.0, args.timeout),
        read=args.timeout,
        write=min(30.0, args.timeout),
        pool=min(10.0, args.timeout),
    )
    reports = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(args.runs):
            report = await probe_sse_delivery(
                base_url=args.base_url,
                route=args.route,
                conversation_id=args.conversation_id,
                library_item_ids=args.library_item_id,
                timeout_seconds=args.timeout,
                cancel_after_first_token=args.cancel_after_first_token,
                client=client,
            )
            reports.append(report.safe_dict())
    return reports


def summarize_reports(reports: list[dict[str, object]]) -> dict[str, object]:
    metrics = {
        name: MeasurementSeries()
        for name in (
            "first_status_ms",
            "first_token_ms",
            "citations_ready_ms",
            "persisting_ms",
            "done_ms",
        )
    }
    failures: list[str] = []
    buffered = 0
    for report in reports:
        errors = report["validation_errors"]
        if report["error"] or errors:
            failures.append(str(report["error"] or errors))
            continue
        buffered += int(report["appears_buffered"] is True)
        for name, series in metrics.items():
            value = report[name]
            if isinstance(value, (int, float)):
                series.add_success(value)
    return {
        "runs": len(reports),
        "success_count": len(reports) - len(failures),
        "failure_count": len(failures),
        "buffered_count": buffered,
        "failure_types": sorted(set(failures)),
        "metrics": {name: series.summary() for name, series in metrics.items()},
    }


def main() -> int:
    args = parse_args()
    reports = asyncio.run(run_probes(args))
    safe = reports[0]
    summary = summarize_reports(reports)
    if args.json_output:
        print(
            json.dumps(
                {"summary": summary, "reports": reports},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Target: {safe['base_url']}")
        print(f"Route: {safe['route']}")
        print(f"HTTP status: {safe['status_code']}")
        print(f"Network chunks: {safe['network_chunk_count']}")
        print(f"First status: {safe['first_status_ms']} ms")
        print(f"First token: {safe['first_token_ms']} ms")
        print(f"Citations ready: {safe['citations_ready_ms']} ms")
        print(f"Done: {safe['done_ms']} ms")
        print(f"Appears buffered: {safe['appears_buffered']}")
        print(f"Validation errors: {safe['validation_errors']}")
        print(f"Error: {safe['error']}")
        if args.runs > 1:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
