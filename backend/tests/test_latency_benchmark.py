from scripts.benchmark_agent_latency import (
    ScenarioResult,
    percentile,
    print_results,
    run_benchmark,
    summarize,
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
