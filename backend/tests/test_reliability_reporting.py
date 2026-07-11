import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.reliability.reporting import (
    EmbeddingDimensionMismatch,
    MeasurementSeries,
    missing_real_provider_configuration,
    safe_environment_report,
    validate_embedding_dimension,
)


def test_measurement_summary_excludes_failures_from_percentiles() -> None:
    series = MeasurementSeries(values=[10, 20, 30], failures=["TimeoutError"])
    summary = series.summary()
    assert summary["p50"] == 20
    assert summary["p95"] == 29
    assert summary["success_count"] == 3
    assert summary["failure_count"] == 1


def test_real_provider_configuration_is_disabled_and_missing_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.pla_real_provider_tests is False
    assert missing_real_provider_configuration(settings, "deepseek")
    assert missing_real_provider_configuration(settings, "zhipu")
    assert missing_real_provider_configuration(settings, "tavily")


def test_safe_report_never_contains_provider_keys_or_full_urls() -> None:
    settings = Settings(
        _env_file=None,
        deepseek_api_key="secret-deepseek",
        zhipu_api_key="secret-zhipu",
        tavily_api_key="secret-tavily",
        deepseek_base_url="https://api.deepseek.example/private/path",
    )
    serialized = str(safe_environment_report(settings))
    assert "secret-" not in serialized
    assert "/private/path" not in serialized
    assert "api.deepseek.example" in serialized


def test_embedding_dimension_validation_stops_mismatched_writes() -> None:
    validate_embedding_dimension(actual=2048, configured=2048, schema=2048)
    with pytest.raises(EmbeddingDimensionMismatch, match="actual=1024"):
        validate_embedding_dimension(actual=1024, configured=2048, schema=2048)


def test_fault_injection_cannot_be_enabled_in_production() -> None:
    with pytest.raises(ValidationError, match="cannot be enabled in production"):
        Settings(
            _env_file=None,
            app_env="production",
            pla_fault_injection_enabled=True,
        )
