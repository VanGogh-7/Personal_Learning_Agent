import asyncio
import socket

import httpx
import pytest

from app.mcp.servers.fetch import (
    FetchSecurityError,
    SecurePageFetcher,
    validate_public_url,
    validate_response_peer,
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fd00:ec2::254]/latest/meta-data/",
    ],
)
async def test_fetch_blocks_ssrf_targets(url: str) -> None:
    with pytest.raises(FetchSecurityError):
        await validate_public_url(url)


@pytest.mark.anyio
async def test_fetch_checks_redirect_target_and_size_limit() -> None:
    def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    redirect_client = httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler))
    fetcher = SecurePageFetcher(redirect_client)
    with pytest.raises(FetchSecurityError, match="blocked"):
        await fetcher.fetch("http://93.184.216.34/start", max_characters=2000)
    await redirect_client.aclose()

    def large_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"x" * 1_000_001,
        )

    large_client = httpx.AsyncClient(transport=httpx.MockTransport(large_handler))
    fetcher = SecurePageFetcher(large_client)
    with pytest.raises(FetchSecurityError, match="size limit"):
        await fetcher.fetch("http://93.184.216.34/page", max_characters=2000)
    await large_client.aclose()


@pytest.mark.anyio
async def test_fetch_timeout_and_html_sanitization() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timeout_client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
    fetcher = SecurePageFetcher(timeout_client)
    with pytest.raises(httpx.ReadTimeout):
        await fetcher.fetch("http://93.184.216.34/page", max_characters=2000)
    await timeout_client.aclose()

    def html_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html><style>secret</style><body>Hello <b>world</b></body></html>",
        )

    html_client = httpx.AsyncClient(transport=httpx.MockTransport(html_handler))
    fetcher = SecurePageFetcher(html_client)
    result = await fetcher.fetch("http://93.184.216.34/page", max_characters=2000)
    assert result["content"] == "Hello world"
    await html_client.aclose()


@pytest.mark.anyio
async def test_fetch_rejects_mixed_public_and_private_dns_answers(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def mixed_getaddrinfo(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", port)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", mixed_getaddrinfo)
    with pytest.raises(FetchSecurityError, match="non-public"):
        await validate_public_url("https://rebinding.example/page")


def test_fetch_rejects_private_connected_peer_after_dns_resolution() -> None:
    class NetworkStream:
        def get_extra_info(self, name):
            assert name == "server_addr"
            return ("::ffff:169.254.169.254", 80)

    response = httpx.Response(
        200,
        extensions={"network_stream": NetworkStream()},
    )
    with pytest.raises(FetchSecurityError, match="public address"):
        validate_response_peer(response)


@pytest.mark.anyio
async def test_fetch_limits_redirects_content_type_and_declared_size() -> None:
    def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "http://93.184.216.34/again"},
        )

    redirect_client = httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler))
    fetcher = SecurePageFetcher(redirect_client)
    fetcher.max_redirects = 1
    with pytest.raises(FetchSecurityError, match="Too many redirects"):
        await fetcher.fetch("http://93.184.216.34/start", max_characters=2_000)
    await redirect_client.aclose()

    def invalid_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": "999999999",
            },
            content=b"binary",
        )

    invalid_client = httpx.AsyncClient(transport=httpx.MockTransport(invalid_response))
    fetcher = SecurePageFetcher(invalid_client)
    with pytest.raises(FetchSecurityError, match="content type"):
        await fetcher.fetch("http://93.184.216.34/page", max_characters=2_000)
    await invalid_client.aclose()


@pytest.mark.anyio
async def test_fetch_total_timeout_bounds_slow_transport() -> None:
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, headers={"Content-Type": "text/plain"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(slow_handler))
    fetcher = SecurePageFetcher(client)
    fetcher.total_timeout = 0.01
    with pytest.raises(TimeoutError):
        await fetcher.fetch("http://93.184.216.34/page", max_characters=2_000)
    await client.aclose()
