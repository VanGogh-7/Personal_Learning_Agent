from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import RLock
from typing import Iterator

from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers import OpenAICompatibleEmbeddingProvider
from app.embeddings.native import GeminiEmbeddingProvider
from app.llm.native import AnthropicLLMProvider, GeminiLLMProvider
from app.llm.providers import LLMProvider, OpenAICompatibleLLMProvider
from app.observability.latency import current_latency_trace
from app.providers.http_clients import provider_http_clients
from app.settings.catalog import get_provider_entry
from app.settings.schemas import ProviderProfileInput


@dataclass(frozen=True)
class ProviderRuntimeSnapshot:
    profile_id: str
    provider: str
    model: str
    chat: LLMProvider | None = None
    embedding: EmbeddingProvider | None = None
    embedding_index_version_id: str | None = None


_chat_snapshot: ContextVar[ProviderRuntimeSnapshot | None] = ContextVar(
    "pla_chat_provider_snapshot", default=None
)
_embedding_snapshot: ContextVar[ProviderRuntimeSnapshot | None] = ContextVar(
    "pla_embedding_provider_snapshot", default=None
)


class ProviderRuntimeRegistry:
    """Process-local active clients; requests retain immutable snapshots."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._profiles: dict[str, ProviderRuntimeSnapshot] = {}
        self._active: dict[str, str] = {}

    def activate(
        self,
        profile_id: str,
        profile: ProviderProfileInput,
        api_key: str | None,
        *,
        embedding_index_version_id: str | None = None,
    ) -> ProviderRuntimeSnapshot:
        snapshot = self._build(
            profile_id,
            profile,
            api_key,
            embedding_index_version_id=embedding_index_version_id,
        )
        with self._lock:
            self._profiles[profile_id] = snapshot
            self._active[profile.kind] = profile_id
        return snapshot

    def deactivate(self, kind: str) -> None:
        with self._lock:
            self._active.pop(kind, None)

    def get_active(self, kind: str) -> ProviderRuntimeSnapshot | None:
        with self._lock:
            profile_id = self._active.get(kind)
            return self._profiles.get(profile_id) if profile_id else None

    def remove(self, profile_id: str) -> None:
        with self._lock:
            self._profiles.pop(profile_id, None)
            for kind, active_id in list(self._active.items()):
                if active_id == profile_id:
                    self._active.pop(kind, None)

    def reset(self) -> None:
        with self._lock:
            self._profiles.clear()
            self._active.clear()

    def _build(
        self,
        profile_id: str,
        profile: ProviderProfileInput,
        api_key: str | None,
        *,
        embedding_index_version_id: str | None,
    ) -> ProviderRuntimeSnapshot:
        entry = get_provider_entry(profile.provider)
        if entry.runtime_status != "available":
            raise ValueError(
                f"{entry.label} requires a native adapter that is not enabled in this build"
            )
        secret = (api_key or "").strip()
        if entry.requires_api_key and not secret:
            raise ValueError(f"{entry.label} requires an API key")
        base_url = profile.base_url or (
            entry.default_chat_base_url
            if profile.kind == "chat"
            else entry.default_embedding_base_url
        )
        if not base_url:
            raise ValueError(f"{entry.label} requires a Base URL")
        headers = dict(profile.extra_headers)
        if profile.kind == "chat":
            if not entry.capabilities.chat or not entry.capabilities.streaming:
                raise ValueError(
                    "The selected Provider cannot satisfy Agent chat capabilities"
                )
            common = {
                "api_key": secret,
                "base_url": base_url,
                "model": profile.model,
                "client": provider_http_clients.get("llm"),
                "async_client": provider_http_clients.get_async("llm"),
                "temperature": profile.temperature,
                "max_output_tokens": profile.max_output_tokens,
            }
            if profile.provider == "anthropic":
                provider = AnthropicLLMProvider(**common)
            elif profile.provider == "gemini":
                provider = GeminiLLMProvider(**common)
            else:
                provider = OpenAICompatibleLLMProvider(**common, extra_headers=headers)
            return ProviderRuntimeSnapshot(
                profile_id, profile.provider, profile.model, chat=provider
            )
        if not entry.capabilities.embeddings:
            raise ValueError("The selected Provider does not support embeddings")
        common_embedding = {
            "api_key": secret,
            "base_url": base_url,
            "model": profile.model,
            "dimension": profile.embedding_dimension,
            "client": provider_http_clients.get("embedding"),
        }
        if profile.provider == "gemini":
            provider = GeminiEmbeddingProvider(**common_embedding)
        else:
            provider = OpenAICompatibleEmbeddingProvider(
                **common_embedding, batch_size=profile.batch_size
            )
        return ProviderRuntimeSnapshot(
            profile_id,
            profile.provider,
            profile.model,
            embedding=provider,
            embedding_index_version_id=embedding_index_version_id,
        )


provider_runtime_registry = ProviderRuntimeRegistry()


def current_chat_provider() -> LLMProvider | None:
    snapshot = _chat_snapshot.get() or provider_runtime_registry.get_active("chat")
    _trace_snapshot(snapshot)
    return snapshot.chat if snapshot else None


def current_embedding_provider() -> EmbeddingProvider | None:
    snapshot = _embedding_snapshot.get() or provider_runtime_registry.get_active(
        "embedding"
    )
    _trace_snapshot(snapshot)
    return snapshot.embedding if snapshot else None


def current_embedding_index_version_id() -> str | None:
    snapshot = _embedding_snapshot.get() or provider_runtime_registry.get_active(
        "embedding"
    )
    return snapshot.embedding_index_version_id if snapshot else None


def capture_provider_snapshots() -> tuple[
    ProviderRuntimeSnapshot | None, ProviderRuntimeSnapshot | None
]:
    return (
        provider_runtime_registry.get_active("chat"),
        provider_runtime_registry.get_active("embedding"),
    )


@contextmanager
def provider_request_snapshot(
    snapshots: tuple[ProviderRuntimeSnapshot | None, ProviderRuntimeSnapshot | None]
    | None = None,
) -> Iterator[None]:
    chat, embedding = snapshots or capture_provider_snapshots()
    chat_token = _chat_snapshot.set(chat)
    embedding_token = _embedding_snapshot.set(embedding)
    try:
        yield
    finally:
        _chat_snapshot.reset(chat_token)
        _embedding_snapshot.reset(embedding_token)


def _trace_snapshot(snapshot: ProviderRuntimeSnapshot | None) -> None:
    trace = current_latency_trace()
    if trace is not None and snapshot is not None:
        prefix = "llm" if snapshot.chat is not None else "embedding"
        trace.set_counter(f"{prefix}_provider", snapshot.provider)
        trace.set_counter(f"{prefix}_model", snapshot.model)
