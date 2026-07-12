import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from mcp.types import CallToolResult

from app.mcp.client import MCPClientManager, MCPError, MCPServerExitedError
from app.mcp.config import MCPServerConfig, SERVER_TOOL_ALLOWLISTS
from app.observability.latency import AgentLatencyTrace, latency_trace_context


def config(**changes) -> MCPServerConfig:
    base = MCPServerConfig(
        name="fetch",
        transport="stdio",
        command=sys.executable,
        args=("-c", "pass"),
        allowed_tools=SERVER_TOOL_ALLOWLISTS["fetch"],
        enabled=True,
        connect_timeout_seconds=1,
        tool_timeout_seconds=1,
        total_timeout_seconds=2,
        max_retries=0,
        retry_backoff_seconds=0,
        max_pending_calls=4,
    )
    return replace(base, **changes)


class SuccessfulSession:
    def __init__(self, *, tools=("fetch",)) -> None:
        self.tools = tools
        self.tool_calls = 0
        self.discovery_calls = 0

    async def initialize(self):
        return None

    async def list_tools(self):
        self.discovery_calls += 1
        return SimpleNamespace(
            tools=[SimpleNamespace(name=name) for name in self.tools]
        )

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.tool_calls += 1
        return CallToolResult(content=[], structuredContent={"url": arguments["url"]})


def test_disabled_server_health_does_not_start_a_runtime() -> None:
    manager = MCPClientManager({"fetch": config(enabled=False)})
    assert manager.health_snapshot()["fetch"]["status"] == "disabled"
    assert manager.active_process_count() == 0


@pytest.mark.anyio
async def test_health_check_discovers_only_and_reports_missing_allowlist() -> None:
    session = SuccessfulSession(tools=())

    @asynccontextmanager
    async def factory(server_config):
        yield session

    manager = MCPClientManager({"fetch": config()}, session_factory=factory)
    assert await manager.health_check("fetch") is False
    health = manager.health_snapshot()["fetch"]
    assert health["status"] == "degraded"
    assert health["missing_allowed_tools"] == ["fetch"]
    assert session.discovery_calls == 2
    assert session.tool_calls == 0
    await manager.shutdown()
    assert manager.health_snapshot()["fetch"]["status"] == "unavailable"


@pytest.mark.anyio
async def test_discovery_failure_marks_server_unavailable() -> None:
    class Session(SuccessfulSession):
        async def list_tools(self):
            raise httpx.ReadError("connection dropped")

    @asynccontextmanager
    async def factory(server_config):
        yield Session()

    manager = MCPClientManager({"fetch": config()}, session_factory=factory)
    assert await manager.health_check("fetch") is False
    health = manager.health_snapshot()["fetch"]
    assert health["status"] == "unavailable"
    assert health["consecutive_failures"] >= 1
    assert health["last_error_category"] in {"connection", "discovery"}
    await manager.shutdown()


@pytest.mark.anyio
async def test_retry_is_bounded_restarts_transport_and_records_health() -> None:
    opened = 0
    closed = 0

    class Session(SuccessfulSession):
        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            if opened == 1:
                raise httpx.ReadError("connection dropped")
            return await super().call_tool(name, arguments, read_timeout_seconds)

    @asynccontextmanager
    async def factory(server_config):
        nonlocal opened, closed
        opened += 1
        try:
            yield Session()
        finally:
            closed += 1

    manager = MCPClientManager(
        {
            "fetch": config(
                transport="streamable_http",
                command=None,
                args=(),
                url="https://mcp.example.test",
                max_retries=1,
            )
        },
        session_factory=factory,
    )
    trace = AgentLatencyTrace(request_id="retry-test")
    with latency_trace_context(trace):
        result = await manager.call_tool("fetch", "fetch", {"url": "https://x.test"})
    assert result == {"url": "https://x.test"}
    assert opened == 2
    assert closed == 1
    assert trace.counters["mcp_retry_count"] == 1
    assert trace.counters["mcp_server_restart_count"] == 1
    health = manager.health_snapshot()["fetch"]
    assert health["status"] == "healthy"
    assert health["restart_count"] == 1
    await manager.shutdown()
    assert closed == 2


@pytest.mark.anyio
async def test_retry_stops_at_configured_limit() -> None:
    opened = 0

    class Session(SuccessfulSession):
        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            raise httpx.ReadError("connection dropped")

    @asynccontextmanager
    async def factory(server_config):
        nonlocal opened
        opened += 1
        yield Session()

    manager = MCPClientManager(
        {"fetch": config(max_retries=1)}, session_factory=factory
    )
    with pytest.raises(MCPServerExitedError):
        await manager.call_tool("fetch", "fetch", {"url": "https://x.test"})
    assert opened == 2
    await manager.shutdown()


@pytest.mark.anyio
async def test_calls_are_serialized_per_server_and_keep_results_isolated() -> None:
    active = 0
    maximum = 0

    class Session(SuccessfulSession):
        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return CallToolResult(
                content=[], structuredContent={"url": arguments["url"]}
            )

    @asynccontextmanager
    async def factory(server_config):
        yield Session()

    manager = MCPClientManager({"fetch": config()}, session_factory=factory)
    results = await asyncio.gather(
        manager.call_tool("fetch", "fetch", {"url": "https://one.test"}),
        manager.call_tool("fetch", "fetch", {"url": "https://two.test"}),
    )
    assert maximum == 1
    assert results == [
        {"url": "https://one.test"},
        {"url": "https://two.test"},
    ]
    await manager.shutdown()


@pytest.mark.anyio
async def test_shutdown_releases_current_and_queued_calls_without_restart() -> None:
    started = asyncio.Event()

    class Session(SuccessfulSession):
        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            started.set()
            await asyncio.Event().wait()

    @asynccontextmanager
    async def factory(server_config):
        yield Session()

    manager = MCPClientManager({"fetch": config()}, session_factory=factory)
    first = asyncio.create_task(
        manager.call_tool("fetch", "fetch", {"url": "https://one.test"})
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(
        manager.call_tool("fetch", "fetch", {"url": "https://two.test"})
    )
    await asyncio.sleep(0)
    await manager.shutdown()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(outcome, MCPError) for outcome in outcomes)
    assert manager.active_process_count() == 0
    assert not any(
        task.get_name().startswith("pla-mcp-") and not task.done()
        for task in asyncio.all_tasks()
    )


@pytest.mark.anyio
async def test_safe_structured_log_excludes_tool_payload(caplog) -> None:
    @asynccontextmanager
    async def factory(server_config):
        yield SuccessfulSession()

    manager = MCPClientManager({"fetch": config()}, session_factory=factory)
    secret = "secret-query-value"
    with caplog.at_level(logging.INFO, logger="app.mcp.client"):
        await manager.call_tool("fetch", "fetch", {"url": secret})
    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.message.startswith("{")
    ]
    assert payloads[-1]["server"] == "fetch"
    assert payloads[-1]["tool"] == "fetch"
    assert secret not in caplog.text
    await manager.shutdown()
