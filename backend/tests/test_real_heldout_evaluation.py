from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evaluation.heldout import (
    benchmark_query_temperatures,
    load_heldout_bundle,
)
from app.llm.providers import get_llm_provider
from app.reliability.reporting import missing_real_provider_configuration

pytestmark = [pytest.mark.real_provider, pytest.mark.network]


def test_real_deepseek_heldout_temperature_and_stability_benchmark() -> None:
    settings = get_settings()
    if not settings.pla_real_provider_tests:
        pytest.skip("PLA_REAL_PROVIDER_TESTS is disabled")
    missing = missing_real_provider_configuration(settings, "deepseek")
    if missing:
        pytest.skip("Missing real DeepSeek configuration: " + ", ".join(missing))
    root = Path("evals/heldout")
    bundle = load_heldout_bundle(
        root / "cases.jsonl", root / "labels.jsonl", root / "claims.jsonl"
    )
    bundle.cases = bundle.cases[:5]
    bundle.labels = {case.case_id: bundle.labels[case.case_id] for case in bundle.cases}
    report = benchmark_query_temperatures(bundle, provider=get_llm_provider(), runs=2)
    assert report["temperature_zero"]["schema_valid_rate"] is not None
    assert report["temperature_zero"]["latency_ms"]["success_count"] > 0
