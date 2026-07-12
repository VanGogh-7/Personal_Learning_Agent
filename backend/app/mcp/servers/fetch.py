from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from typing import Any, AsyncIterator
from urllib.parse import urljoin, urlsplit

import httpx
from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings

ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain", "application/xhtml+xml"})
BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


class FetchSecurityError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and data.strip():
            self.parts.append(data.strip())


class SecurePageFetcher:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=settings.mcp_connect_timeout_seconds,
                read=settings.mcp_fetch_read_timeout_seconds,
                write=settings.mcp_fetch_read_timeout_seconds,
                pool=settings.mcp_connect_timeout_seconds,
            ),
            headers={"User-Agent": settings.academic_api_user_agent},
        )
        self._owns_client = client is None
        self.max_bytes = settings.mcp_fetch_max_response_bytes
        self.max_redirects = settings.mcp_fetch_max_redirects
        self.total_timeout = settings.mcp_fetch_total_timeout_seconds

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, url: str, *, max_characters: int) -> dict[str, Any]:
        target = url.strip()
        async with asyncio.timeout(self.total_timeout):
            for redirect_index in range(self.max_redirects + 1):
                await validate_public_url(target)
                async with self._client.stream("GET", target) as response:
                    if response.is_redirect:
                        if redirect_index >= self.max_redirects:
                            raise FetchSecurityError("Too many redirects")
                        location = response.headers.get("location")
                        if not location:
                            raise FetchSecurityError("Redirect has no target")
                        target = urljoin(target, location)
                        await validate_public_url(target)
                        continue
                    validate_response_peer(response)
                    response.raise_for_status()
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise FetchSecurityError("Unsupported response content type")
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise FetchSecurityError(
                                "Response content length is invalid"
                            ) from exc
                        if declared_size > self.max_bytes:
                            raise FetchSecurityError("Response exceeds size limit")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_bytes:
                            raise FetchSecurityError("Response exceeds size limit")
                    text = body.decode(response.encoding or "utf-8", errors="replace")
                    if content_type in {"text/html", "application/xhtml+xml"}:
                        text = html_to_text(text)
                    return {
                        "url": target,
                        "content": text[: max(1_000, min(max_characters, 50_000))],
                        "content_type": content_type,
                        "truncated": len(text) > max_characters,
                    }
        raise FetchSecurityError("Fetch did not produce a response")


async def validate_public_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise FetchSecurityError("Invalid URL") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise FetchSecurityError("Only HTTP and HTTPS URLs are allowed")
    if not parsed.hostname or parsed.username or parsed.password:
        raise FetchSecurityError("URL host is invalid")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise FetchSecurityError("Local hosts are blocked")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise FetchSecurityError("URL port is invalid") from exc
    try:
        literal = ipaddress.ip_address(hostname)
        addresses = [literal]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            resolved = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise FetchSecurityError("URL host could not be resolved") from exc
        addresses = list(
            {ipaddress.ip_address(item[4][0]) for item in resolved if item[4]}
        )
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise FetchSecurityError("Private or non-public network targets are blocked")


def html_to_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def validate_response_peer(response: httpx.Response) -> None:
    """Reject a private peer after connect to reduce DNS-rebinding exposure."""
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        return
    peer = stream.get_extra_info("server_addr")
    if not isinstance(peer, tuple) or not peer:
        return
    try:
        address = ipaddress.ip_address(str(peer[0]))
    except ValueError as exc:
        raise FetchSecurityError("Connected peer address is invalid") from exc
    if not _is_public_address(address):
        raise FetchSecurityError("Connected peer is not a public address")


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Treat IPv4-mapped IPv6 as its IPv4 target before applying policy."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global


_fetcher: SecurePageFetcher | None = None


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[dict[str, Any]]:
    global _fetcher
    _fetcher = SecurePageFetcher()
    try:
        yield {"fetcher": _fetcher}
    finally:
        await _fetcher.close()
        _fetcher = None


mcp = FastMCP("PLA Secure Fetch", lifespan=lifespan, json_response=True)


@mcp.tool(name="fetch", structured_output=True)
async def fetch(url: str, max_characters: int = 12_000) -> dict[str, Any]:
    """Fetch one preselected public HTTP(S) page with SSRF and size controls."""
    if _fetcher is None:
        raise RuntimeError("Secure Fetch MCP is not ready")
    return await _fetcher.fetch(url, max_characters=max_characters)


if __name__ == "__main__":
    mcp.run(transport="stdio")
