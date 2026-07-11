import asyncio
import json

import pytest

from app.api.agent_routes import should_include_debug_timings
from app.core.config import Settings
from app.observability.latency import (
    AgentLatencyTrace,
    current_latency_trace,
    latency_trace_context,
    measure_latency,
    measure_latency_sync,
)


@pytest.mark.anyio
async def test_timing_helper_records_successful_stage() -> None:
    trace = AgentLatencyTrace()
    async with measure_latency("success", trace):
        await asyncio.sleep(0)
    assert trace.timings_ms["success"] >= 0


def test_timing_helper_records_failed_stage() -> None:
    trace = AgentLatencyTrace()
    with pytest.raises(RuntimeError):
        with measure_latency_sync("failure", trace):
            raise RuntimeError("expected")
    assert trace.timings_ms["failure"] >= 0


def test_multiple_calls_to_same_stage_are_accumulated() -> None:
    trace = AgentLatencyTrace()
    with measure_latency_sync("repeat", trace):
        pass
    first = trace.timings_ms["repeat"]
    with measure_latency_sync("repeat", trace):
        pass
    assert trace.timings_ms["repeat"] >= first
    assert trace.counters["repeat_count"] == 2


@pytest.mark.anyio
async def test_parallel_requests_keep_isolated_traces() -> None:
    async def worker(request_id: str) -> tuple[str, str | None]:
        trace = AgentLatencyTrace(request_id=request_id)
        with latency_trace_context(trace):
            await asyncio.sleep(0)
            current = current_latency_trace()
            return request_id, current.request_id if current else None

    results = await asyncio.gather(worker("one"), worker("two"))
    assert results == [("one", "one"), ("two", "two")]
    assert current_latency_trace() is None


def test_sensitive_fields_are_excluded_from_summary() -> None:
    trace = AgentLatencyTrace(request_id="request-safe")
    payload = trace.summary(event="agent_request_completed")
    encoded = json.dumps(payload)
    assert "prompt" not in payload
    assert "question" not in payload
    assert "answer" not in payload
    assert '"embedding": [' not in encoded
    assert "api_key" not in encoded


def test_debug_timings_disabled_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        agent_debug_timings_in_response=True,
    )
    assert should_include_debug_timings(settings) is False


def test_debug_timings_require_explicit_development_flag() -> None:
    disabled = Settings(
        _env_file=None,
        app_env="development",
        agent_debug_timings_in_response=False,
    )
    enabled = Settings(
        _env_file=None,
        app_env="development",
        agent_debug_timings_in_response=True,
    )
    assert should_include_debug_timings(disabled) is False
    assert should_include_debug_timings(enabled) is True
