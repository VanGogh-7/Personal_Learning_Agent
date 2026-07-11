import os
import subprocess
import sys
from pathlib import Path

from scripts.benchmark_agent_latency import (
    ScenarioResult,
    percentile,
    print_results,
    run_benchmark,
    summarize,
)
from scripts.benchmark_agent_streaming import (
    StreamScenarioResult,
    print_results as print_stream_results,
)


def test_percentile_summary_and_failed_runs(capsys) -> None:
    calls = 0

    def sometimes_fails() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("expected")

    results = run_benchmark(
        {"smoke": sometimes_fails},
        runs=3,
        warmups=0,
    )
    assert len(results["smoke"].values_ms) == 2
    assert results["smoke"].failures == ["RuntimeError"]
    stats = summarize([1.0, 2.0, 3.0])
    assert stats["p50"] == 2.0
    assert percentile([1.0, 2.0, 3.0], 0.95) == 2.9
    print_results(results)
    output = capsys.readouterr().out
    assert "p95" in output
    assert "smoke" in output


def test_empty_result_is_reported_without_percentile(capsys) -> None:
    print_results({"failed": ScenarioResult(failures=["RuntimeError"])})
    assert "failed" in capsys.readouterr().out


def test_stream_benchmark_reports_milestones_and_failures(capsys) -> None:
    print_stream_results(
        {
            "local_only": StreamScenarioResult(
                metrics_ms={"first_status": [10.0, 20.0], "first_token": [30.0]},
                event_counts=[8],
                token_counts=[2],
                failures=["RuntimeError"],
            )
        }
    )
    output = capsys.readouterr().out
    assert "first_status" in output
    assert "first_token" in output
    assert "p95" in output
    assert "failed=1" in output


def test_real_benchmark_refuses_to_run_without_explicit_enablement() -> None:
    environment = dict(os.environ)
    environment["PLA_REAL_PROVIDER_TESTS"] = "false"
    result = subprocess.run(
        [
            sys.executable,
            str(Path("scripts/benchmark_real_providers.py")),
            "--confirm-costs",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Real benchmarks are disabled" in result.stderr + result.stdout


def test_soak_script_requires_explicit_confirmation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/soak_agent_sse.py", "--runs", "1"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Soak is opt-in" in result.stderr + result.stdout
