import pytest

from app.core.config import Settings
from app.mcp.client import MCPError
from app.mcp.gateway import MCPToolGateway


class RecordingManager:
    def __init__(self) -> None:
        self.calls = []

    async def call_tool(self, server, tool, arguments):
        self.calls.append((server, tool, arguments))
        return {}


@pytest.mark.anyio
async def test_gateway_validates_arguments_before_calling_transport() -> None:
    manager = RecordingManager()
    gateway = MCPToolGateway(manager=manager, settings=Settings())
    with pytest.raises(MCPError, match="arguments were rejected"):
        await gateway.call(
            "fetch",
            "fetch",
            {"url": "file:///etc/passwd", "unknown": "secret"},
        )
    assert manager.calls == []
    assert gateway.call_count == 0


@pytest.mark.anyio
async def test_gateway_applies_schema_defaults_and_request_budget() -> None:
    manager = RecordingManager()
    gateway = MCPToolGateway(
        manager=manager,
        settings=Settings(mcp_max_calls_per_request=1),
    )
    await gateway.call("fetch", "fetch", {"url": "https://example.com"})
    assert manager.calls == [
        (
            "fetch",
            "fetch",
            {"url": "https://example.com", "max_characters": 12_000},
        )
    ]
    with pytest.raises(MCPError, match="budget was exhausted"):
        await gateway.call("fetch", "fetch", {"url": "https://example.org"})


@pytest.mark.anyio
async def test_gateway_rejects_tools_without_an_approved_schema() -> None:
    manager = RecordingManager()
    gateway = MCPToolGateway(manager=manager, settings=Settings())
    with pytest.raises(MCPError, match="arguments were rejected"):
        await gateway.call("fetch", "new-unreviewed-tool", {})
    assert manager.calls == []
