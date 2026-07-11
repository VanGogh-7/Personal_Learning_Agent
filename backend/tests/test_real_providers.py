import asyncio

import pytest

from app.agents.web_research import get_web_research_provider
from app.core.config import get_settings
from app.embeddings.base import EMBEDDING_DIMENSION
from app.embeddings.providers import get_embedding_provider
from app.reliability.reporting import (
    missing_real_provider_configuration,
    validate_embedding_dimension,
)
from app.reliability.sse_probe import probe_sse_delivery
from scripts.benchmark_real_providers import (
    SHORT_PROMPT,
    TAVILY_QUERY,
    measure_deepseek,
)

pytestmark = [pytest.mark.real_provider, pytest.mark.network]


def _require(provider: str) -> None:
    settings = get_settings()
    if not settings.pla_real_provider_tests:
        pytest.skip("PLA_REAL_PROVIDER_TESTS is disabled")
    missing = missing_real_provider_configuration(settings, provider)
    if missing:
        pytest.skip("Missing real Provider configuration: " + ", ".join(missing))


@pytest.mark.anyio
async def test_real_deepseek_short_stream() -> None:
    _require("deepseek")
    measured = await measure_deepseek(SHORT_PROMPT, max_tokens=1024)
    assert measured.first_token_ms > 0
    assert measured.total_ms >= measured.first_token_ms
    assert measured.output_characters > 0
    assert measured.finish_reason is not None


def test_real_zhipu_embedding_dimension() -> None:
    _require("zhipu")
    provider = get_embedding_provider()
    embedding = provider.embed_text("Real dimension validation for PLA.")
    validate_embedding_dimension(
        actual=len(embedding),
        configured=provider.dimension,
        schema=EMBEDDING_DIMENSION,
    )


def test_real_tavily_search() -> None:
    _require("tavily")
    result = get_web_research_provider().research(TAVILY_QUERY)
    assert result.status == "available"
    assert result.sources


@pytest.mark.parametrize("route", ["local_only", "web_only", "both"])
def test_real_agent_route_sse(route: str) -> None:
    settings = get_settings()
    if not settings.pla_real_provider_tests:
        pytest.skip("PLA_REAL_PROVIDER_TESTS is disabled")
    report = asyncio.run(
        probe_sse_delivery(
            base_url=settings.pla_sse_target_url,
            route=route,
            timeout_seconds=max(120.0, settings.llm_read_timeout_seconds),
        )
    )
    assert report.error is None
    assert report.validate() == []
    assert report.appears_buffered() is False
