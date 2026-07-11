from __future__ import annotations

from threading import RLock

import httpx

from app.core.config import Settings, get_settings


class ProviderHttpClientManager:
    """Own reusable HTTP clients for synchronous provider boundaries."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._clients: dict[str, httpx.Client] = {}

    def get(self, provider_kind: str, settings: Settings | None = None) -> httpx.Client:
        resolved = settings or get_settings()
        with self._lock:
            client = self._clients.get(provider_kind)
            if client is not None and not client.is_closed:
                return client
            if provider_kind == "llm":
                timeout = httpx.Timeout(
                    connect=resolved.llm_connect_timeout_seconds,
                    read=resolved.llm_read_timeout_seconds,
                    write=resolved.llm_read_timeout_seconds,
                    pool=resolved.llm_connect_timeout_seconds,
                )
            elif provider_kind == "embedding":
                timeout = httpx.Timeout(
                    connect=resolved.embedding_connect_timeout_seconds,
                    read=resolved.embedding_read_timeout_seconds,
                    write=resolved.embedding_read_timeout_seconds,
                    pool=resolved.embedding_connect_timeout_seconds,
                )
            else:
                raise ValueError(f"Unknown provider client kind: {provider_kind}")
            client = httpx.Client(timeout=timeout)
            self._clients[provider_kind] = client
            return client

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()


provider_http_clients = ProviderHttpClientManager()
