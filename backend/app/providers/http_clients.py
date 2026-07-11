from __future__ import annotations

from threading import RLock

import httpx

from app.core.config import Settings, get_settings


class ProviderHttpClientManager:
    """Own reusable HTTP clients for synchronous provider boundaries."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._clients: dict[str, httpx.Client] = {}
        self._async_clients: dict[str, httpx.AsyncClient] = {}

    def get(self, provider_kind: str, settings: Settings | None = None) -> httpx.Client:
        resolved = settings or get_settings()
        with self._lock:
            client = self._clients.get(provider_kind)
            if client is not None and not client.is_closed:
                return client
            timeout = self._timeout(provider_kind, resolved)
            client = httpx.Client(timeout=timeout)
            self._clients[provider_kind] = client
            return client

    def get_async(
        self, provider_kind: str, settings: Settings | None = None
    ) -> httpx.AsyncClient:
        resolved = settings or get_settings()
        with self._lock:
            client = self._async_clients.get(provider_kind)
            if client is not None and not client.is_closed:
                return client
            timeout = self._timeout(provider_kind, resolved)
            client = httpx.AsyncClient(timeout=timeout)
            self._async_clients[provider_kind] = client
            return client

    async def aclose(self) -> None:
        with self._lock:
            clients = list(self._async_clients.values())
            self._async_clients.clear()
        for client in clients:
            await client.aclose()

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()

    @staticmethod
    def _timeout(provider_kind: str, settings: Settings) -> httpx.Timeout:
        if provider_kind == "llm":
            return httpx.Timeout(
                connect=settings.llm_connect_timeout_seconds,
                read=settings.llm_read_timeout_seconds,
                write=settings.llm_read_timeout_seconds,
                pool=settings.llm_connect_timeout_seconds,
            )
        if provider_kind == "embedding":
            return httpx.Timeout(
                connect=settings.embedding_connect_timeout_seconds,
                read=settings.embedding_read_timeout_seconds,
                write=settings.embedding_read_timeout_seconds,
                pool=settings.embedding_connect_timeout_seconds,
            )
        if provider_kind == "web":
            return httpx.Timeout(
                connect=settings.tavily_connect_timeout_seconds,
                read=settings.tavily_read_timeout_seconds,
                write=settings.tavily_read_timeout_seconds,
                pool=settings.tavily_connect_timeout_seconds,
            )
        raise ValueError(f"Unknown provider client kind: {provider_kind}")


provider_http_clients = ProviderHttpClientManager()
