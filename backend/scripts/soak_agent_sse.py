"""Run an explicit repeated/cancellation PLA SSE soak against a live backend."""

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
from app.reliability.reporting import MeasurementSeries, safe_environment_report
from app.reliability.sse_probe import probe_sse_delivery


async def run_soak(
    *,
    base_url: str,
    route: str,
    runs: int,
    cancel_every: int,
    timeout_seconds: float,
    library_item_ids: list[str] | None = None,
) -> dict[str, object]:
    first_status = MeasurementSeries()
    first_token = MeasurementSeries()
    total = MeasurementSeries()
    successes = 0
    cancellations = 0
    validation_failures: list[str] = []
    timeout = httpx.Timeout(
        connect=min(10.0, timeout_seconds),
        read=timeout_seconds,
        write=min(30.0, timeout_seconds),
        pool=min(10.0, timeout_seconds),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        for index in range(1, runs + 1):
            cancel = cancel_every > 0 and index % cancel_every == 0
            report = await probe_sse_delivery(
                base_url=base_url,
                route=route,
                timeout_seconds=timeout_seconds,
                cancel_after_first_token=cancel,
                library_item_ids=library_item_ids,
                client=client,
            )
            if cancel:
                cancellations += int(report.cancelled_by_client)
                if report.error:
                    validation_failures.append(report.error)
                continue
            errors = report.validate()
            if report.error or errors:
                validation_failures.extend(errors or [report.error or "unknown"])
                continue
            successes += 1
            first_status.add_success(report.milestone_ms("status") or 0)
            first_token.add_success(report.milestone_ms("token") or 0)
            total.add_success(report.milestone_ms("done") or 0)
    return {
        "runs": runs,
        "successes": successes,
        "cancellations": cancellations,
        "failure_count": len(validation_failures),
        "failure_types": sorted(set(validation_failures)),
        "first_status_ms": first_status.summary(),
        "first_token_ms": first_token.summary(),
        "total_ms": total.summary(),
        "http_client_closed": client.is_closed,
    }


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=settings.pla_sse_target_url)
    parser.add_argument(
        "--route",
        choices=["local_only", "web_only", "both"],
        default="both",
    )
    parser.add_argument("--runs", type=int, default=settings.pla_sse_soak_runs)
    parser.add_argument("--cancel-every", type=int, default=0)
    parser.add_argument("--library-item-id", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--confirm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm:
        raise SystemExit(
            "Soak is opt-in and may consume Provider quota. Pass --confirm to run."
        )
    report = {
        "environment": safe_environment_report(get_settings()),
        "target": args.base_url,
        "result": asyncio.run(
            run_soak(
                base_url=args.base_url,
                route=args.route,
                runs=args.runs,
                cancel_every=args.cancel_every,
                timeout_seconds=args.timeout,
                library_item_ids=args.library_item_id,
            )
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    result = report["result"]
    return 1 if isinstance(result, dict) and result["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
