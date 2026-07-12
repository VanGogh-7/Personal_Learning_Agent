import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.settings_routes as settings_routes
from app.db.base import Base
from app.db.vector_search import search_similar_chunks_for_documents
from app.embeddings.mock import MockEmbeddingProvider
from app.embeddings.providers import get_embedding_provider
from app.llm.providers import DeterministicLLMProvider, get_llm_provider
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.embedding_index import ChunkEmbedding, EmbeddingIndexVersion
from app.models.provider_profile import ProviderProfile
from app.providers.http_clients import provider_http_clients
from app.settings.catalog import get_provider_entry
from app.settings.runtime import (
    ProviderRuntimeRegistry,
    current_chat_provider,
    provider_request_snapshot,
    provider_runtime_registry,
)
from app.settings.schemas import ProviderConnectionTestRequest, ProviderProfileInput
from app.settings.service import (
    activate_profile,
    create_profile,
    list_profiles,
    profile_to_read,
    reindex_embedding_profile,
    test_provider_connection as run_provider_connection_test,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture(autouse=True)
def reset_runtime_registry():
    provider_runtime_registry.reset()
    yield
    provider_runtime_registry.reset()


def chat_profile(**updates) -> ProviderProfileInput:
    values = {
        "kind": "chat",
        "name": "Custom chat",
        "provider": "custom_openai_compatible",
        "base_url": "https://models.example/v1",
        "model": "chat-model",
        "secret_ref": "provider:chat",
        "temperature": 0.2,
        "max_output_tokens": 1000,
    }
    values.update(updates)
    return ProviderProfileInput.model_validate(values)


def embedding_profile(**updates) -> ProviderProfileInput:
    values = {
        "kind": "embedding",
        "name": "Custom embeddings",
        "provider": "custom_openai_compatible",
        "base_url": "https://models.example/v1",
        "model": "embedding-model",
        "secret_ref": "provider:embedding",
        "embedding_dimension": 3,
        "batch_size": 8,
    }
    values.update(updates)
    return ProviderProfileInput.model_validate(values)


def test_profile_validation_and_native_capability_differences() -> None:
    with pytest.raises(ValueError, match="Embedding dimension"):
        ProviderProfileInput.model_validate(
            {
                "kind": "embedding",
                "name": "broken",
                "provider": "zhipu",
                "base_url": "https://example.test",
                "model": "embedding-3",
            }
        )
    with pytest.raises(ValueError, match="non-secret extra headers"):
        chat_profile(extra_headers={"X-Api-Key": "must-not-be-metadata"})
    anthropic = get_provider_entry("anthropic")
    gemini = get_provider_entry("gemini")
    assert anthropic.capabilities.native_adapter is True
    assert anthropic.capabilities.embeddings is False
    assert anthropic.runtime_status == "available"
    assert gemini.capabilities.embeddings is True
    assert gemini.runtime_status == "available"


def test_profile_metadata_never_contains_api_key(session: Session) -> None:
    payload = chat_profile(api_key="secret-value")
    profile = create_profile(session, payload)
    response = profile_to_read(profile).model_dump()
    stored = session.get(ProviderProfile, profile.id)
    assert "api_key" not in response
    assert "secret-value" not in json.dumps(response)
    assert stored is not None
    assert "secret-value" not in repr(stored.__dict__)
    assert response["api_key_mask"] == "••••••••"


def test_embedding_profile_creates_pending_index_and_cannot_activate(
    session: Session,
) -> None:
    profile = create_profile(session, embedding_profile())
    version = session.execute(
        select(EmbeddingIndexVersion).where(
            EmbeddingIndexVersion.embedding_profile_id == profile.id
        )
    ).scalar_one()
    assert version.status == "pending"
    with pytest.raises(ValueError, match="re-indexed"):
        activate_profile(session, profile.id, "secret")


def test_profile_switch_does_not_change_active_request_snapshot() -> None:
    registry = provider_runtime_registry
    first = registry.activate("first", chat_profile(model="first"), "key")
    with provider_request_snapshot():
        registry.activate("second", chat_profile(model="second"), "key")
        assert current_chat_provider() is first.chat
    assert current_chat_provider() is registry.get_active("chat").chat
    assert registry.get_active("chat").model == "second"


def test_openai_compatible_connection_test_and_client_reuse(monkeypatch) -> None:
    client = httpx.Client(transport=httpx.MockTransport(_chat_transport))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(_chat_transport))
    monkeypatch.setattr(
        provider_http_clients,
        "get",
        lambda kind, settings=None: client,
    )
    monkeypatch.setattr(
        provider_http_clients,
        "get_async",
        lambda kind, settings=None: async_client,
    )
    result = asyncio.run(async_test_provider(chat_profile(api_key="secret")))
    assert result.success is True
    assert result.capabilities.streaming is True
    registry = ProviderRuntimeRegistry()
    one = registry.activate("one", chat_profile(model="one"), "secret")
    two = registry.activate("two", chat_profile(model="two"), "secret")
    assert one.chat._client is two.chat._client  # type: ignore[attr-defined]


async def async_test_provider(profile: ProviderProfileInput):
    request = ProviderConnectionTestRequest.model_validate(profile.model_dump())
    return await run_provider_connection_test(request)


def test_embedding_connection_dimension_mismatch(monkeypatch) -> None:
    def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(
        provider_http_clients, "get", lambda kind, settings=None: client
    )
    result = asyncio.run(async_test_provider(embedding_profile(api_key="secret")))
    assert result.success is False
    assert "2 dimensions; expected 3" in result.message


def test_provider_timeout_is_normalized_without_secret(monkeypatch) -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sk-sensitive-value", request=request)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(
        provider_http_clients, "get", lambda kind, settings=None: client
    )
    monkeypatch.setattr(
        provider_http_clients,
        "get_async",
        lambda kind, settings=None: async_client,
    )
    result = asyncio.run(
        async_test_provider(chat_profile(api_key="sk-sensitive-value"))
    )
    assert result.success is False
    assert "sk-sensitive-value" not in result.message
    assert "LLMProviderError" in result.message


def test_versioned_vectors_do_not_mix_between_profiles(session: Session) -> None:
    document = Document(title="Doc", file_path="doc.txt", file_type="txt")
    session.add(document)
    session.flush()
    first_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="first",
        char_start=0,
        char_end=5,
        embedding=None,
    )
    second_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="second",
        char_start=6,
        char_end=12,
        embedding=None,
    )
    session.add_all([first_chunk, second_chunk])
    profile_one = create_profile(session, embedding_profile(name="one"))
    profile_two = create_profile(session, embedding_profile(name="two"))
    session.flush()
    version_one = session.execute(
        select(EmbeddingIndexVersion).where(
            EmbeddingIndexVersion.embedding_profile_id == profile_one.id
        )
    ).scalar_one()
    version_two = session.execute(
        select(EmbeddingIndexVersion).where(
            EmbeddingIndexVersion.embedding_profile_id == profile_two.id
        )
    ).scalar_one()
    session.add_all(
        [
            ChunkEmbedding(
                chunk_id=first_chunk.id,
                index_version_id=version_one.id,
                embedding=[0.0, 0.0, 0.0],
            ),
            ChunkEmbedding(
                chunk_id=second_chunk.id,
                index_version_id=version_two.id,
                embedding=[0.0, 0.0, 0.0],
            ),
        ]
    )
    session.flush()
    provider_runtime_registry.activate(
        str(profile_one.id),
        embedding_profile(name="one"),
        "secret",
        embedding_index_version_id=str(version_one.id),
    )
    results = search_similar_chunks_for_documents(
        session, [0.0, 0.0, 0.0], [document.id]
    )
    assert [item.chunk_id for item in results] == [first_chunk.id]


def test_reindex_builds_new_space_without_overwriting_legacy_vectors(
    monkeypatch, session: Session
) -> None:
    document = Document(title="Doc", file_path="doc.txt", file_type="txt")
    session.add(document)
    session.flush()
    legacy = [0.0] * 2048
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="versioned content",
        char_start=0,
        char_end=17,
        embedding=legacy,
    )
    session.add(chunk)
    profile = create_profile(session, embedding_profile())

    def transport(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [0.1, 0.2, 0.3]}
                    for index, _ in enumerate(payload["input"])
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(
        provider_http_clients, "get", lambda kind, settings=None: client
    )
    version = reindex_embedding_profile(session, profile.id, "secret")
    session.refresh(chunk)
    assert version.status == "ready"
    assert version.embedded_chunks == 1
    assert list(chunk.embedding) == legacy
    versioned = session.execute(
        select(ChunkEmbedding).where(ChunkEmbedding.index_version_id == version.id)
    ).scalar_one()
    assert list(versioned.embedding) == [0.1, 0.2, 0.3]


def test_no_desktop_profiles_preserves_environment_fallback() -> None:
    assert isinstance(get_llm_provider(), DeterministicLLMProvider)
    assert isinstance(get_embedding_provider(), MockEmbeddingProvider)


def test_settings_api_response_masks_secret(monkeypatch, session: Session) -> None:
    monkeypatch.setattr(settings_routes, "get_db_session", lambda: session)
    client = TestClient(app)
    response = client.post(
        "/api/settings/profiles",
        json={
            **chat_profile(api_key=None).model_dump(mode="json"),
            "secret_ref": "provider:secret",
        },
    )
    assert response.status_code == 200
    serialized = response.text
    assert "secret-value" not in serialized
    assert 'api_key"' not in serialized
    assert response.json()["api_key_mask"] == "••••••••"


def test_list_profiles_tracks_independent_active_kinds(session: Session) -> None:
    chat = create_profile(session, chat_profile())
    embedding = create_profile(session, embedding_profile())
    chat.is_active = True
    embedding.is_active = False
    summary = list_profiles(session)
    assert summary.active_chat_profile == str(chat.id)
    assert summary.active_embedding_profile is None


def test_profile_read_distinguishes_persisted_and_runtime_activation(
    session: Session,
) -> None:
    profile = create_profile(session, chat_profile())
    profile.is_active = True

    stale = profile_to_read(profile)
    assert stale.is_active is True
    assert stale.runtime_active is False

    provider_runtime_registry.activate(str(profile.id), chat_profile(), "secret")
    active = profile_to_read(profile)
    assert active.runtime_active is True


def _chat_transport(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    if payload.get("stream"):
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"OK"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )
    content = '{"ok":true}' if payload.get("response_format") else "OK"
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
