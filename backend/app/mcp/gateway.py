from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.mcp.client import MCPClientManager, MCPError, mcp_client_manager
from app.mcp.tool_schemas import validate_tool_arguments


class MCPToolGateway:
    """Bounded request-scoped gateway over the process MCP client manager."""

    def __init__(
        self,
        manager: MCPClientManager | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.manager = manager or mcp_client_manager
        self.settings = settings or get_settings()
        self.call_count = 0

    async def call(
        self, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | list[Any]:
        if self.call_count >= self.settings.mcp_max_calls_per_request:
            raise MCPError("MCP request call budget was exhausted")
        try:
            validated = validate_tool_arguments(server, tool, arguments)
        except ValueError as exc:
            raise MCPError("MCP tool arguments were rejected") from exc
        self.call_count += 1
        return await self.manager.call_tool(server, tool, validated)
