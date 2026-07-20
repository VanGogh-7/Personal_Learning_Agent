import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult

from app.mcp.client import MCPClientManager, MCPError, MCPToolNotAllowedError
from app.mcp.config import (
    MCPServerConfig,
    SERVER_TOOL_ALLOWLISTS,
    build_mcp_server_configs,
)
from app.core.config import Settings
from app.observability.latency import AgentLatencyTrace, latency_trace_context


def config(name: str, transport: str = "stdio") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport=transport,  # type: ignore[arg-type]
        command=sys.executable if transport == "stdio" else None,
        args=("-c", "pass") if transport == "stdio" else (),
        url="https://example.test/mcp" if transport == "streamable_http" else None,
        allowed_tools=SERVER_TOOL_ALLOWLISTS[name],
        enabled=True,
        connect_timeout_seconds=2,
        tool_timeout_seconds=2,
    )


def test_mcp_config_validates_stdio_http_and_allowlist() -> None:
    config("fetch").validate()
    config("tavily", "streamable_http").validate()
    invalid = MCPServerConfig(
        name="fetch",
        transport="stdio",
        command="python",
        allowed_tools=frozenset({"read_local_file"}),
    )
    with pytest.raises(ValueError, match="allowlist"):
        invalid.validate()
    secret = MCPServerConfig(
        name="tavily",
        transport="streamable_http",
        url="https://example.test/mcp",
        headers={"Authorization": "Bearer secret-value"},
        allowed_tools=SERVER_TOOL_ALLOWLISTS["tavily"],
    )
    assert "secret-value" not in repr(secret)


def test_mcp_provider_credentials_are_backend_only_and_required_for_search() -> None:
    missing = build_mcp_server_configs(
        Settings(
            _env_file=None,
            mcp_enabled=True,
            tavily_api_key="",
            brave_api_key="",
        )
    )
    assert missing["tavily"].enabled is False
    assert missing["brave"].enabled is False
    assert missing["fetch"].enabled is True
    assert missing["academic"].enabled is True

    configured = build_mcp_server_configs(
        Settings(
            _env_file=None,
            mcp_enabled=True,
            tavily_api_key="tavily-secret",
            brave_api_key="brave-secret",
        )
    )
    assert configured["tavily"].env == {"TAVILY_API_KEY": "tavily-secret"}
    assert configured["tavily"].headers == {"Authorization": "Bearer tavily-secret"}
    assert configured["brave"].env["BRAVE_API_KEY"] == "brave-secret"
    assert "tavily-secret" not in repr(configured["tavily"])
    assert "brave-secret" not in repr(configured["brave"])


@pytest.mark.anyio
async def test_tool_discovery_is_allowlisted_and_session_is_reused() -> None:
    opened = 0
    closed = 0
    calls: list[str] = []

    class Session:
        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name="fetch"), SimpleNamespace(name="unsafe")]
            )

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            calls.append(name)
            return CallToolResult(
                content=[], structuredContent={"content": arguments["url"]}
            )

    @asynccontextmanager
    async def factory(server_config):
        nonlocal opened, closed
        opened += 1
        try:
            yield Session()
        finally:
            closed += 1

    manager = MCPClientManager({"fetch": config("fetch")}, session_factory=factory)
    await manager.startup()
    assert await manager.discover_tools("fetch") == frozenset({"fetch"})
    trace = AgentLatencyTrace(request_id="mcp-test")
    with latency_trace_context(trace):
        first = await manager.call_tool("fetch", "fetch", {"url": "one"})
        second = await manager.call_tool("fetch", "fetch", {"url": "two"})
    assert first == {"content": "one"}
    assert second == {"content": "two"}
    assert opened == 1
    assert calls == ["fetch", "fetch"]
    assert trace.counters["mcp_call_count"] == 2
    assert "mcp_connect" in trace.timings_ms
    assert "mcp_tool_discovery" in trace.timings_ms
    assert "mcp_tool_call" in trace.timings_ms
    with pytest.raises(MCPToolNotAllowedError):
        await manager.call_tool("fetch", "unsafe", {})
    await manager.shutdown()
    assert closed == 1


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["stdio", "streamable_http"])
async def test_stdio_and_streamable_http_runtime_lifecycle(transport: str) -> None:
    observed: list[str] = []

    class Session:
        async def initialize(self):
            observed.append("initialize")

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="fetch")])

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            return CallToolResult(content=[], structuredContent={})

    @asynccontextmanager
    async def factory(server_config):
        observed.append(server_config.transport)
        try:
            yield Session()
        finally:
            observed.append("closed")

    manager = MCPClientManager(
        {"fetch": config("fetch", transport)}, session_factory=factory
    )
    assert await manager.health_check("fetch") is True
    await manager.shutdown()
    assert observed == [transport, "initialize", "closed"]


@pytest.mark.anyio
async def test_cancellation_closes_runtime_and_allows_reconnect() -> None:
    closed = 0

    class Session:
        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="fetch")])

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            await asyncio.Event().wait()

    @asynccontextmanager
    async def factory(server_config):
        nonlocal closed
        try:
            yield Session()
        finally:
            closed += 1

    manager = MCPClientManager({"fetch": config("fetch")}, session_factory=factory)
    trace = AgentLatencyTrace(request_id="cancel-test")
    with latency_trace_context(trace):
        task = asyncio.create_task(manager.call_tool("fetch", "fetch", {"url": "x"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed == 1
    assert trace.counters["mcp_cancelled_count"] == 1
    assert manager.health_snapshot()["fetch"]["status"] == "unavailable"
    assert await manager.health_check("fetch") is True
    await manager.shutdown()
    assert closed == 2


@pytest.mark.anyio
async def test_local_academic_stdio_server_tool_discovery() -> None:
    academic = MCPServerConfig(
        name="academic",
        transport="stdio",
        command=sys.executable,
        args=("-m", "app.mcp.servers.academic"),
        allowed_tools=SERVER_TOOL_ALLOWLISTS["academic"],
        enabled=True,
        connect_timeout_seconds=10,
        tool_timeout_seconds=10,
    )
    manager = MCPClientManager({"academic": academic})
    tools = await manager.discover_tools("academic")
    assert tools == SERVER_TOOL_ALLOWLISTS["academic"]
    assert manager.active_process_count() == 1
    await manager.shutdown()
    assert manager.active_process_count() == 0
    assert not any(
        task.get_name().startswith("pla-mcp-") and not task.done()
        for task in asyncio.all_tasks()
    )


@pytest.mark.anyio
async def test_sync_bridge_uses_manager_event_loop() -> None:
    manager = MCPClientManager({})
    await manager.startup()

    async def value() -> str:
        return "ok"

    result = await asyncio.to_thread(manager.run_sync, value(), timeout_seconds=1)
    assert result == "ok"
    await manager.shutdown()


@pytest.mark.anyio
async def test_tool_timeout_is_bounded_and_normalized() -> None:
    class Session:
        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="fetch")])

        async def call_tool(self, name, arguments, read_timeout_seconds=None):
            await asyncio.Event().wait()

    @asynccontextmanager
    async def factory(server_config):
        yield Session()

    fetch_config = replace(config("fetch"), tool_timeout_seconds=0.01)
    manager = MCPClientManager({"fetch": fetch_config}, session_factory=factory)
    with pytest.raises(MCPError, match="timed out"):
        await manager.call_tool("fetch", "fetch", {"url": "x"})
    await manager.shutdown()
