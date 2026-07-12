from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from app.core.config import Settings, get_settings

MCPTransport = Literal["stdio", "streamable_http"]

SERVER_TOOL_ALLOWLISTS: dict[str, frozenset[str]] = {
    "tavily": frozenset({"tavily-search", "tavily-extract"}),
    "brave": frozenset({"brave_web_search", "brave_news_search"}),
    "fetch": frozenset({"fetch"}),
    "academic": frozenset(
        {"search_arxiv", "search_openalex", "lookup_doi", "get_paper_metadata"}
    ),
}


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: MCPTransport
    allowed_tools: frozenset[str]
    enabled: bool = True
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict, repr=False)
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    connect_timeout_seconds: float = 10.0
    tool_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 45.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.2
    max_concurrency: int = 1
    max_pending_calls: int = 20

    def validate(self) -> None:
        if self.name not in SERVER_TOOL_ALLOWLISTS:
            raise ValueError(f"Unknown MCP server: {self.name}")
        if not self.allowed_tools or not self.allowed_tools.issubset(
            SERVER_TOOL_ALLOWLISTS[self.name]
        ):
            raise ValueError(f"Invalid tool allowlist for MCP server: {self.name}")
        if self.transport == "stdio":
            if not self.command or not self.command.strip():
                raise ValueError(f"STDIO MCP server {self.name} requires a command")
        elif self.transport == "streamable_http":
            parsed = urlsplit(self.url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    f"Streamable HTTP MCP server {self.name} requires an HTTP URL"
                )
        else:
            raise ValueError(f"Unsupported MCP transport: {self.transport}")
        if (
            self.connect_timeout_seconds <= 0
            or self.tool_timeout_seconds <= 0
            or self.total_timeout_seconds <= 0
        ):
            raise ValueError("MCP timeouts must be positive")
        if self.max_retries < 0 or self.max_retries > 2:
            raise ValueError("MCP retries must be between zero and two")
        if self.max_concurrency != 1:
            raise ValueError("MCP sessions currently require serialized tool calls")
        if self.max_pending_calls < 1:
            raise ValueError("MCP pending-call limit must be positive")


def build_mcp_server_configs(
    settings: Settings | None = None,
) -> dict[str, MCPServerConfig]:
    resolved = settings or get_settings()
    common = {
        "connect_timeout_seconds": resolved.mcp_connect_timeout_seconds,
        "tool_timeout_seconds": resolved.mcp_tool_timeout_seconds,
        "total_timeout_seconds": resolved.mcp_total_timeout_seconds,
        "max_retries": resolved.mcp_max_retries,
        "retry_backoff_seconds": resolved.mcp_retry_backoff_seconds,
        "max_pending_calls": resolved.mcp_max_pending_calls_per_server,
    }
    configs = {
        "tavily": MCPServerConfig(
            name="tavily",
            transport=_transport(resolved.mcp_tavily_transport),
            command=resolved.mcp_tavily_command,
            args=tuple(resolved.mcp_tavily_args),
            url=resolved.mcp_tavily_url,
            env={"TAVILY_API_KEY": resolved.tavily_api_key},
            headers={"Authorization": f"Bearer {resolved.tavily_api_key}"},
            allowed_tools=SERVER_TOOL_ALLOWLISTS["tavily"],
            enabled=resolved.mcp_enabled and bool(resolved.tavily_api_key.strip()),
            **common,
        ),
        "brave": MCPServerConfig(
            name="brave",
            transport=_transport(resolved.mcp_brave_transport),
            command=resolved.mcp_brave_command,
            args=tuple(resolved.mcp_brave_args),
            url=resolved.mcp_brave_url,
            env={
                "BRAVE_API_KEY": resolved.brave_api_key,
                "BRAVE_MCP_ENABLED_TOOLS": "brave_web_search brave_news_search",
            },
            allowed_tools=SERVER_TOOL_ALLOWLISTS["brave"],
            enabled=resolved.mcp_enabled and bool(resolved.brave_api_key.strip()),
            **common,
        ),
        "fetch": MCPServerConfig(
            name="fetch",
            transport=_transport(resolved.mcp_fetch_transport),
            command=resolved.mcp_fetch_command,
            args=tuple(resolved.mcp_fetch_args),
            url=resolved.mcp_fetch_url,
            allowed_tools=SERVER_TOOL_ALLOWLISTS["fetch"],
            enabled=resolved.mcp_enabled,
            **common,
        ),
        "academic": MCPServerConfig(
            name="academic",
            transport=_transport(resolved.mcp_academic_transport),
            command=resolved.mcp_academic_command,
            args=tuple(resolved.mcp_academic_args),
            url=resolved.mcp_academic_url,
            allowed_tools=SERVER_TOOL_ALLOWLISTS["academic"],
            enabled=resolved.mcp_enabled,
            **common,
        ),
    }
    for config in configs.values():
        config.validate()
    return configs


def _transport(value: str) -> MCPTransport:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"stdio", "streamable_http"}:
        raise ValueError(f"Unsupported MCP transport: {value}")
    return normalized  # type: ignore[return-value]
