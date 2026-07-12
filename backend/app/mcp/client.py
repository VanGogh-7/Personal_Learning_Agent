from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, AsyncIterator, Awaitable, Literal, Protocol, TypeVar

import httpx
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from app.mcp.config import MCPServerConfig, build_mcp_server_configs
from app.observability.latency import current_latency_trace

logger = logging.getLogger(__name__)
T = TypeVar("T")
MCPHealthStatus = Literal["disabled", "starting", "healthy", "degraded", "unavailable"]
MCPErrorCategory = Literal[
    "cancelled",
    "connection",
    "discovery",
    "server_exit",
    "timeout",
    "tool_error",
    "validation",
]


class MCPError(RuntimeError):
    """Safe MCP boundary error without raw tool payloads or secrets."""

    category: MCPErrorCategory = "tool_error"
    retryable: bool = False


class MCPRetryableError(MCPError):
    retryable = True


class MCPConnectionError(MCPRetryableError):
    category: MCPErrorCategory = "connection"


class MCPDiscoveryError(MCPRetryableError):
    category: MCPErrorCategory = "discovery"


class MCPServerExitedError(MCPRetryableError):
    category: MCPErrorCategory = "server_exit"


class MCPTimeoutError(MCPRetryableError):
    category: MCPErrorCategory = "timeout"


class MCPToolExecutionError(MCPRetryableError):
    category: MCPErrorCategory = "tool_error"


class MCPToolNotAllowedError(MCPError):
    category: MCPErrorCategory = "validation"


class MCPSession(Protocol):
    async def initialize(self) -> Any: ...

    async def list_tools(self) -> Any: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> CallToolResult: ...


@dataclass
class MCPServerHealth:
    server: str
    transport: str
    status: MCPHealthStatus
    discovered_tools: frozenset[str] = frozenset()
    missing_allowed_tools: frozenset[str] = frozenset()
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    last_error_category: MCPErrorCategory | None = None
    restart_count: int = 0

    def safe_dict(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "transport": self.transport,
            "status": self.status,
            "discovered_tools": sorted(self.discovered_tools),
            "missing_allowed_tools": sorted(self.missing_allowed_tools),
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "consecutive_failures": self.consecutive_failures,
            "last_error_category": self.last_error_category,
            "restart_count": self.restart_count,
        }


@dataclass
class _ToolCommand:
    tool: str
    arguments: dict[str, Any]
    future: asyncio.Future[dict[str, Any] | list[Any]]


@dataclass
class _HealthCommand:
    future: asyncio.Future[frozenset[str]]


MCPCommand = _ToolCommand | _HealthCommand | None


@dataclass
class _ServerRuntime:
    config: MCPServerConfig
    queue: asyncio.Queue[MCPCommand]
    ready: asyncio.Future[frozenset[str]]
    task: asyncio.Task[None] | None = None
    current: MCPCommand = None
    start_ms: float = 0.0
    connect_ms: float = 0.0
    discovery_ms: float = 0.0
    metrics_reported: bool = False
    expected_stop: bool = False


class MCPClientManager:
    """Own bounded, reusable MCP transports in dedicated lifecycle tasks."""

    def __init__(
        self,
        configs: dict[str, MCPServerConfig] | None = None,
        *,
        session_factory=None,
    ) -> None:
        self._configs = configs
        self._session_factory = session_factory or open_mcp_session
        self._runtimes: dict[str, _ServerRuntime] = {}
        self._health: dict[str, MCPServerHealth] = {}
        self._lock = asyncio.Lock()
        self._started = False
        self._shutdown = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._initialize_health()

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._started = True
        self._shutdown = False
        self._initialize_health()

    async def shutdown(self) -> None:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
            self._started = False
            self._shutdown = True
        await asyncio.gather(
            *(self._stop_runtime(runtime) for runtime in runtimes),
            return_exceptions=True,
        )
        for health in self._health.values():
            if health.status != "disabled":
                health.status = "unavailable"
        self._loop = None
        self._set_active_process_counter()

    def run_sync(self, awaitable: Awaitable[T], *, timeout_seconds: float) -> T:
        """Run MCP work on the lifespan loop from the legacy sync endpoint."""
        loop = self._loop
        if loop is None or loop.is_closed():
            _close_awaitable(awaitable)
            raise MCPError("MCP client manager is not running")
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            _close_awaitable(awaitable)
            raise MCPError("Synchronous MCP bridge cannot run on the MCP event loop")
        future = asyncio.run_coroutine_threadsafe(awaitable, loop)
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError as exc:
            future.cancel()
            raise MCPTimeoutError("MCP research timed out") from exc

    async def discover_tools(self, server: str) -> frozenset[str]:
        runtime = await self._runtime(server)
        try:
            tools = await asyncio.wait_for(
                asyncio.shield(runtime.ready),
                timeout=runtime.config.connect_timeout_seconds,
            )
            self._record_start_metrics(server, runtime)
            return tools
        except TimeoutError as exc:
            error = MCPTimeoutError(f"MCP server {server} connection timed out")
            self._record_failure(server, error.category, unavailable=True)
            await self._discard_runtime(server, runtime)
            raise error from exc
        except asyncio.CancelledError:
            await self._discard_runtime(server, runtime)
            raise
        except Exception as exc:
            error = _safe_mcp_error(exc, MCPConnectionError)
            self._record_failure(server, error.category, unavailable=True)
            await self._discard_runtime(server, runtime)
            raise error from exc

    async def health_check(self, server: str) -> bool:
        """Run discovery only; never execute a real search as a health probe."""
        try:
            runtime = await self._runtime(server)
            await self.discover_tools(server)
            future: asyncio.Future[frozenset[str]] = (
                asyncio.get_running_loop().create_future()
            )
            async with asyncio.timeout(runtime.config.total_timeout_seconds):
                await runtime.queue.put(_HealthCommand(future=future))
                discovered = await future
            self._record_discovery_health(runtime.config, discovered)
            return not self._health[server].missing_allowed_tools
        except asyncio.CancelledError:
            self._increment_trace("mcp_cancelled_count")
            self._record_cancelled(server)
            runtime = self._runtimes.get(server)
            if runtime is not None:
                await self._discard_runtime(server, runtime)
            raise
        except Exception as exc:
            error = _safe_mcp_error(exc, MCPDiscoveryError)
            self._record_failure(server, error.category, unavailable=True)
            runtime = self._runtimes.get(server)
            if runtime is not None:
                await self._discard_runtime(server, runtime)
            return False

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        self._initialize_health()
        return {
            server: health.safe_dict()
            for server, health in sorted(self._health.items())
        }

    def active_process_count(self) -> int:
        return sum(
            1
            for runtime in self._runtimes.values()
            if runtime.config.transport == "stdio"
            and runtime.task is not None
            and not runtime.task.done()
        )

    async def call_tool(
        self, server: str, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | list[Any]:
        config = self._config(server)
        last_runtime: _ServerRuntime | None = None
        try:
            async with asyncio.timeout(config.total_timeout_seconds):
                for attempt in range(config.max_retries + 1):
                    try:
                        last_runtime = await self._runtime(server, restart=attempt > 0)
                        result = await self._call_once(
                            last_runtime, server, tool, arguments
                        )
                        self._record_success(server)
                        self._log_call(
                            server=server,
                            tool=tool,
                            transport=config.transport,
                            outcome="success",
                        )
                        return result
                    except MCPToolNotAllowedError:
                        raise
                    except MCPRetryableError as exc:
                        self._record_failure(
                            server,
                            exc.category,
                            unavailable=exc.category
                            in {"connection", "discovery", "server_exit"},
                        )
                        if last_runtime is not None:
                            await self._discard_runtime(server, last_runtime)
                            last_runtime = None
                        if attempt >= config.max_retries:
                            self._log_call(
                                server=server,
                                tool=tool,
                                transport=config.transport,
                                outcome="failure",
                                category=exc.category,
                            )
                            raise
                        self._increment_trace("mcp_retry_count")
                        await asyncio.sleep(
                            config.retry_backoff_seconds * (attempt + 1)
                        )
        except TimeoutError as exc:
            error = MCPTimeoutError("MCP total timeout was exceeded")
            self._record_failure(server, error.category)
            if last_runtime is not None:
                await self._discard_runtime(server, last_runtime)
            self._log_call(
                server=server,
                tool=tool,
                transport=config.transport,
                outcome="failure",
                category=error.category,
            )
            raise error from exc
        except asyncio.CancelledError:
            self._increment_trace("mcp_cancelled_count")
            self._record_cancelled(server)
            if last_runtime is not None:
                await self._discard_runtime(server, last_runtime)
            self._log_call(
                server=server,
                tool=tool,
                transport=config.transport,
                outcome="cancelled",
                category="cancelled",
            )
            raise
        raise MCPError("MCP call ended without a result")

    async def _call_once(
        self,
        runtime: _ServerRuntime,
        server: str,
        tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | list[Any]:
        tools = await self.discover_tools(server)
        if tool not in runtime.config.allowed_tools or tool not in tools:
            raise MCPToolNotAllowedError(
                f"MCP tool is not approved for server {server}: {tool}"
            )
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("mcp_call_count")
        future: asyncio.Future[dict[str, Any] | list[Any]] = (
            asyncio.get_running_loop().create_future()
        )
        started_at = perf_counter()
        await runtime.queue.put(
            _ToolCommand(tool=tool, arguments=dict(arguments), future=future)
        )
        try:
            return await future
        except MCPError:
            raise
        except Exception as exc:
            raise MCPToolExecutionError(f"MCP tool {tool} failed on {server}") from exc
        finally:
            if trace is not None:
                trace.record("mcp_tool_call", (perf_counter() - started_at) * 1000)

    async def _runtime(self, server: str, *, restart: bool = False) -> _ServerRuntime:
        if not self._started:
            if self._shutdown:
                raise MCPError("MCP client manager is shutting down")
            await self.startup()
        async with self._lock:
            existing = self._runtimes.get(server)
            if existing is not None and existing.task is not None:
                if not existing.task.done() and not restart:
                    return existing
                self._runtimes.pop(server, None)
                if not existing.task.done():
                    existing.expected_stop = True
                    existing.task.cancel()
            config = self._config(server)
            health = self._ensure_health(config)
            if restart or existing is not None:
                health.restart_count += 1
                self._increment_trace("mcp_server_restart_count")
            health.status = "starting"
            queue: asyncio.Queue[MCPCommand] = asyncio.Queue(
                maxsize=config.max_pending_calls
            )
            ready: asyncio.Future[frozenset[str]] = (
                asyncio.get_running_loop().create_future()
            )
            ready.add_done_callback(_consume_future_exception)
            runtime = _ServerRuntime(config=config, queue=queue, ready=ready)
            runtime.task = asyncio.create_task(
                self._run_server(runtime), name=f"pla-mcp-{server}"
            )
            self._runtimes[server] = runtime
            self._set_active_process_counter()
            return runtime

    def _config(self, server: str) -> MCPServerConfig:
        configs = self._configs or build_mcp_server_configs()
        config = configs.get(server)
        if config is None or not config.enabled:
            if config is not None:
                self._ensure_health(config).status = "disabled"
            raise MCPError(f"MCP server {server} is not configured")
        return config

    async def _run_server(self, runtime: _ServerRuntime) -> None:
        started_at = perf_counter()
        unexpected_error: BaseException | None = None
        try:
            async with self._session_factory(runtime.config) as session:
                runtime.start_ms = (perf_counter() - started_at) * 1000
                connect_started = perf_counter()
                async with asyncio.timeout(runtime.config.connect_timeout_seconds):
                    await session.initialize()
                runtime.connect_ms = (perf_counter() - connect_started) * 1000
                discovery_started = perf_counter()
                async with asyncio.timeout(runtime.config.connect_timeout_seconds):
                    discovered = await session.list_tools()
                runtime.discovery_ms = (perf_counter() - discovery_started) * 1000
                names = frozenset(tool.name for tool in discovered.tools)
                approved = names.intersection(runtime.config.allowed_tools)
                self._record_discovery_health(runtime.config, names)
                if not runtime.ready.done():
                    runtime.ready.set_result(approved)
                while True:
                    command = await runtime.queue.get()
                    runtime.current = command
                    if command is None:
                        return
                    if command.future.cancelled():
                        runtime.current = None
                        continue
                    if isinstance(command, _HealthCommand):
                        await self._run_health_command(session, runtime, command)
                    else:
                        await self._run_tool_command(session, runtime, command)
                    runtime.current = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            unexpected_error = exc
            error = _safe_mcp_error(
                exc,
                MCPDiscoveryError if not runtime.ready.done() else MCPServerExitedError,
            )
            if not runtime.ready.done():
                runtime.ready.set_exception(error)
                self._record_failure(
                    runtime.config.name, error.category, unavailable=True
                )
            elif runtime.current is None:
                self._record_failure(
                    runtime.config.name, error.category, unavailable=True
                )
        finally:
            self._fail_pending(
                runtime,
                MCPServerExitedError(
                    f"MCP server {runtime.config.name} is no longer available"
                ),
            )
            if unexpected_error is not None and not runtime.expected_stop:
                self._log_server_exit(runtime, unexpected_error)
            self._set_active_process_counter()

    async def _run_health_command(
        self,
        session: MCPSession,
        runtime: _ServerRuntime,
        command: _HealthCommand,
    ) -> None:
        try:
            async with asyncio.timeout(runtime.config.tool_timeout_seconds):
                discovered = await session.list_tools()
            names = frozenset(tool.name for tool in discovered.tools)
            command.future.set_result(names)
        except TimeoutError:
            command.future.set_exception(MCPTimeoutError("MCP health check timed out"))
        except Exception as exc:
            command.future.set_exception(
                MCPDiscoveryError("MCP health discovery failed")
            )
            raise MCPServerExitedError("MCP connection was lost") from exc

    async def _run_tool_command(
        self,
        session: MCPSession,
        runtime: _ServerRuntime,
        command: _ToolCommand,
    ) -> None:
        try:
            async with asyncio.timeout(runtime.config.tool_timeout_seconds):
                result = await session.call_tool(
                    command.tool,
                    command.arguments,
                    read_timeout_seconds=timedelta(
                        seconds=runtime.config.tool_timeout_seconds
                    ),
                )
            if result.isError:
                raise MCPToolExecutionError(
                    f"MCP tool {command.tool} returned an error"
                )
            command.future.set_result(_tool_result_payload(result))
        except TimeoutError:
            command.future.set_exception(
                MCPTimeoutError(f"MCP tool {command.tool} timed out")
            )
        except MCPError as exc:
            command.future.set_exception(exc)
        except (
            EOFError,
            ConnectionError,
            httpx.TransportError,
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
            anyio.EndOfStream,
        ) as exc:
            error = MCPServerExitedError(
                f"MCP server {runtime.config.name} connection was lost"
            )
            command.future.set_exception(error)
            raise error from exc
        except Exception as exc:
            command.future.set_exception(
                MCPToolExecutionError(
                    f"MCP tool {command.tool} failed on {runtime.config.name}"
                )
            )
            logger.debug(
                "MCP tool transport exception category=%s",
                type(exc).__name__,
            )

    async def _discard_runtime(self, server: str, runtime: _ServerRuntime) -> None:
        async with self._lock:
            if self._runtimes.get(server) is runtime:
                self._runtimes.pop(server, None)
        await self._stop_runtime(runtime)

    async def _stop_runtime(self, runtime: _ServerRuntime) -> None:
        runtime.expected_stop = True
        self._fail_pending(runtime, MCPError("MCP runtime was stopped"))
        task = runtime.task
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.gather(task, return_exceptions=True),
                    timeout=runtime.config.connect_timeout_seconds,
                )
            except TimeoutError:
                logger.critical(
                    json.dumps(
                        {
                            "event": "mcp_runtime_shutdown_timeout",
                            "server": runtime.config.name,
                            "transport": runtime.config.transport,
                        },
                        separators=(",", ":"),
                    )
                )
        self._set_active_process_counter()

    def _fail_pending(self, runtime: _ServerRuntime, error: MCPError) -> None:
        if not runtime.ready.done():
            runtime.ready.set_exception(error)
        current = runtime.current
        if current is not None and not current.future.done():
            current.future.set_exception(error)
        runtime.current = None
        while not runtime.queue.empty():
            command = runtime.queue.get_nowait()
            if command is not None and not command.future.done():
                command.future.set_exception(error)

    def _initialize_health(self) -> None:
        try:
            configs = self._configs or build_mcp_server_configs()
        except Exception:
            return
        for config in configs.values():
            self._ensure_health(config)

    def _ensure_health(self, config: MCPServerConfig) -> MCPServerHealth:
        health = self._health.get(config.name)
        if health is None:
            health = MCPServerHealth(
                server=config.name,
                transport=config.transport,
                status="unavailable" if config.enabled else "disabled",
            )
            self._health[config.name] = health
        return health

    def _record_discovery_health(
        self, config: MCPServerConfig, discovered: frozenset[str]
    ) -> None:
        health = self._ensure_health(config)
        health.discovered_tools = discovered
        health.missing_allowed_tools = config.allowed_tools.difference(discovered)
        health.status = "degraded" if health.missing_allowed_tools else "healthy"
        health.last_success_at = _utc_now()
        health.consecutive_failures = 0
        health.last_error_category = None

    def _record_success(self, server: str) -> None:
        config = self._config(server)
        health = self._ensure_health(config)
        health.status = "degraded" if health.missing_allowed_tools else "healthy"
        health.last_success_at = _utc_now()
        health.consecutive_failures = 0
        health.last_error_category = None

    def _record_failure(
        self,
        server: str,
        category: MCPErrorCategory,
        *,
        unavailable: bool = False,
    ) -> None:
        try:
            config = self._config(server)
        except MCPError:
            return
        health = self._ensure_health(config)
        health.status = "unavailable" if unavailable else "degraded"
        health.last_failure_at = _utc_now()
        health.consecutive_failures += 1
        health.last_error_category = category
        self._increment_trace("mcp_error_count")
        if category == "timeout":
            self._increment_trace("mcp_timeout_count")

    def _record_cancelled(self, server: str) -> None:
        try:
            config = self._config(server)
        except MCPError:
            return
        health = self._ensure_health(config)
        health.status = "unavailable"
        health.last_failure_at = _utc_now()
        health.last_error_category = "cancelled"

    def _record_start_metrics(self, server: str, runtime: _ServerRuntime) -> None:
        trace = current_latency_trace()
        if trace is None or server in trace._mcp_servers_reported:
            return
        trace._mcp_servers_reported.add(server)
        reused = runtime.metrics_reported
        trace.record("mcp_server_start", 0 if reused else runtime.start_ms)
        trace.record("mcp_connect", 0 if reused else runtime.connect_ms)
        trace.record("mcp_tool_discovery", 0 if reused else runtime.discovery_ms)
        runtime.metrics_reported = True
        self._set_active_process_counter()

    def _set_active_process_counter(self) -> None:
        trace = current_latency_trace()
        if trace is not None:
            trace.set_counter("active_mcp_process_count", self.active_process_count())

    @staticmethod
    def _increment_trace(counter: str) -> None:
        trace = current_latency_trace()
        if trace is not None:
            trace.increment(counter)

    def _log_call(
        self,
        *,
        server: str,
        tool: str,
        transport: str,
        outcome: str,
        category: MCPErrorCategory | None = None,
    ) -> None:
        trace = current_latency_trace()
        payload = {
            "event": "mcp_tool_call_completed",
            "request_id": trace.request_id if trace is not None else None,
            "server": server,
            "tool": tool,
            "transport": transport,
            "outcome": outcome,
            "error_category": category,
        }
        level = logging.INFO if outcome == "success" else logging.WARNING
        logger.log(level, json.dumps(payload, separators=(",", ":")))

    def _log_server_exit(self, runtime: _ServerRuntime, error: BaseException) -> None:
        logger.warning(
            json.dumps(
                {
                    "event": "mcp_server_exited",
                    "server": runtime.config.name,
                    "transport": runtime.config.transport,
                    "error_category": _safe_mcp_error(
                        error, MCPServerExitedError
                    ).category,
                },
                separators=(",", ":"),
            )
        )


@asynccontextmanager
async def open_mcp_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
    async with AsyncExitStack() as stack:
        if config.transport == "stdio":
            errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
            streams = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=config.command or "",
                        args=list(config.args),
                        env={key: value for key, value in config.env.items() if value},
                    ),
                    errlog=errlog,
                )
            )
            read_stream, write_stream = streams
        else:
            client = httpx.AsyncClient(
                headers={key: value for key, value in config.headers.items() if value},
                timeout=httpx.Timeout(
                    connect=config.connect_timeout_seconds,
                    read=config.tool_timeout_seconds,
                    write=config.tool_timeout_seconds,
                    pool=config.connect_timeout_seconds,
                ),
            )
            await stack.enter_async_context(client)
            streams = await stack.enter_async_context(
                streamable_http_client(config.url or "", http_client=client)
            )
            read_stream, write_stream, _ = streams
        session = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=config.tool_timeout_seconds),
        )
        await stack.enter_async_context(session)
        yield session


def _tool_result_payload(result: CallToolResult) -> dict[str, Any] | list[Any]:
    if result.structuredContent is not None:
        return result.structuredContent
    for item in result.content:
        text = getattr(item, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"content": text}
        if isinstance(parsed, (dict, list)):
            return parsed
    return {}


def _safe_mcp_error(
    error: BaseException, default: type[MCPRetryableError]
) -> MCPRetryableError:
    if isinstance(error, MCPRetryableError):
        return error
    return default("MCP operation failed")


def _close_awaitable(awaitable: Awaitable[Any]) -> None:
    if hasattr(awaitable, "close"):
        awaitable.close()  # type: ignore[union-attr]


def _consume_future_exception(future: asyncio.Future[Any]) -> None:
    if not future.cancelled():
        future.exception()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


mcp_client_manager = MCPClientManager()
