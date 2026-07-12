import pytest

from app.core.config import get_settings
from app.mcp.client import MCPClientManager
from app.mcp.config import build_mcp_server_configs
from app.mcp.servers.fetch import FetchSecurityError, validate_public_url

pytestmark = [pytest.mark.real_mcp, pytest.mark.network]


def require_real_mcp(server: str) -> dict:
    settings = get_settings()
    if not settings.mcp_real_tests:
        pytest.skip("MCP_REAL_TESTS is disabled")
    configs = build_mcp_server_configs(settings)
    config = configs[server]
    if not settings.mcp_enabled or not config.enabled:
        pytest.skip(f"MCP server {server} is not configured")
    return configs


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("server", "tool", "arguments"),
    [
        ("tavily", "tavily-search", {"query": "Banach space", "max_results": 2}),
        ("brave", "brave_web_search", {"query": "Banach space", "count": 2}),
        ("academic", "search_arxiv", {"query": "Banach space", "limit": 2}),
        ("fetch", "fetch", {"url": "https://example.com", "max_characters": 2000}),
    ],
)
async def test_real_mcp_tool(server: str, tool: str, arguments: dict) -> None:
    configs = require_real_mcp(server)
    if server == "fetch":
        try:
            await validate_public_url(str(arguments["url"]))
        except FetchSecurityError as exc:
            pytest.skip(f"Network environment cannot safely validate Fetch: {exc}")
    manager = MCPClientManager(configs)
    try:
        result = await manager.call_tool(server, tool, arguments)
        assert result
    finally:
        await manager.shutdown()
