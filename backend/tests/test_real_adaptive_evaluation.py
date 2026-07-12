from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evaluation.adaptive_graph import evaluate_dataset, load_dataset
from app.llm.providers import get_llm_provider
from app.reliability.reporting import missing_real_provider_configuration

pytestmark = [pytest.mark.real_provider, pytest.mark.network]


def test_real_deepseek_query_analysis_json_stability() -> None:
    settings = get_settings()
    if not settings.pla_real_provider_tests:
        pytest.skip("PLA_REAL_PROVIDER_TESTS is disabled")
    missing = missing_real_provider_configuration(settings, "deepseek")
    if missing:
        pytest.skip("Missing real DeepSeek configuration: " + ", ".join(missing))
    cases = load_dataset(Path("evals/adaptive_graph.jsonl"))[:5]
    report = evaluate_dataset(
        cases,
        variant="adaptive",
        runs=2,
        seed=57,
        provider=get_llm_provider(),
        provider_name=settings.deepseek_model,
    )
    assert report["query_analysis"]["schema_valid_rate"] is not None
    assert report["query_analysis"]["latency_ms"]["success_count"] > 0
