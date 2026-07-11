from __future__ import annotations

import platform
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings


class EmbeddingDimensionMismatch(ValueError):
    """Raised when a real embedding cannot be safely used with the schema."""


@dataclass
class MeasurementSeries:
    values: list[float] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def add_success(self, value: float) -> None:
        self.values.append(float(value))

    def add_failure(self, error: BaseException) -> None:
        self.failures.append(type(error).__name__)

    def summary(self) -> dict[str, float | int | list[str] | None]:
        if not self.values:
            return {
                "count": 0,
                "success_count": 0,
                "failure_count": len(self.failures),
                "min": None,
                "max": None,
                "mean": None,
                "p50": None,
                "p90": None,
                "p95": None,
                "failure_types": sorted(set(self.failures)),
            }
        return {
            "count": len(self.values),
            "success_count": len(self.values),
            "failure_count": len(self.failures),
            "min": min(self.values),
            "max": max(self.values),
            "mean": statistics.fmean(self.values),
            "p50": percentile(self.values, 0.50),
            "p90": percentile(self.values, 0.90),
            "p95": percentile(self.values, 0.95),
            "failure_types": sorted(set(self.failures)),
        }


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires successful values")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def validate_embedding_dimension(*, actual: int, configured: int, schema: int) -> None:
    if actual == configured == schema:
        return
    raise EmbeddingDimensionMismatch(
        "Embedding dimension mismatch: "
        f"actual={actual}, configured={configured}, schema={schema}. "
        "Database writes must remain disabled until a separate schema decision."
    )


def safe_environment_report(settings: Settings) -> dict[str, Any]:
    """Return benchmark context without secrets, prompts, or full endpoints."""
    return {
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "providers": {
            "llm": settings.llm_provider,
            "llm_model": settings.deepseek_model,
            "llm_host": _safe_host(settings.deepseek_base_url),
            "embedding": settings.embedding_provider,
            "embedding_model": settings.zhipu_embedding_model,
            "embedding_host": _safe_host(settings.zhipu_base_url),
            "web": settings.web_research_provider,
            "web_host": _safe_host(settings.tavily_base_url),
        },
        "configured_embedding_dimension": settings.zhipu_embedding_dimension,
    }


def missing_real_provider_configuration(settings: Settings, provider: str) -> list[str]:
    normalized = provider.strip().lower()
    if normalized == "deepseek":
        values = {
            "LLM_PROVIDER=deepseek": settings.llm_provider.lower() == "deepseek",
            "DEEPSEEK_API_KEY": bool(settings.deepseek_api_key.strip()),
        }
    elif normalized == "zhipu":
        values = {
            "EMBEDDING_PROVIDER=zhipu": settings.embedding_provider.lower() == "zhipu",
            "ZHIPU_API_KEY": bool(settings.zhipu_api_key.strip()),
        }
    elif normalized == "tavily":
        values = {
            "WEB_RESEARCH_PROVIDER=tavily": (
                settings.web_research_provider.lower() == "tavily"
            ),
            "TAVILY_API_KEY": bool(settings.tavily_api_key.strip()),
        }
    else:
        raise ValueError(f"Unknown real provider: {provider}")
    return [name for name, configured in values.items() if not configured]


def _safe_host(url: str) -> str | None:
    return urlsplit(url).hostname
