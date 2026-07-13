from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings.providers import EmbeddingProviderError
from app.db.vector_search import active_processing_filter
from app.models.document import Document
from app.llm.providers import LLMProviderError
from app.models.document_chunk import DocumentChunk
from app.models.embedding_index import ChunkEmbedding, EmbeddingIndexVersion
from app.models.provider_profile import ProviderProfile
from app.models.pdf_processing import PdfProcessingVersion
from app.settings.catalog import get_provider_entry
from app.settings.runtime import ProviderRuntimeRegistry, provider_runtime_registry
from app.settings.schemas import (
    EmbeddingIndexVersionRead,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResponse,
    ProviderProfileInput,
    ProviderProfileList,
    ProviderProfileRead,
)


def list_profiles(session: Session) -> ProviderProfileList:
    profiles = (
        session.execute(
            select(ProviderProfile).order_by(ProviderProfile.kind, ProviderProfile.name)
        )
        .scalars()
        .all()
    )
    return ProviderProfileList(
        profiles=[profile_to_read(profile) for profile in profiles],
        active_chat_profile=next(
            (
                str(profile.id)
                for profile in profiles
                if profile.kind == "chat" and profile.is_active
            ),
            None,
        ),
        active_embedding_profile=next(
            (
                str(profile.id)
                for profile in profiles
                if profile.kind == "embedding" and profile.is_active
            ),
            None,
        ),
    )


def create_profile(session: Session, payload: ProviderProfileInput) -> ProviderProfile:
    entry = get_provider_entry(payload.provider)
    capabilities = entry.capabilities
    if payload.kind == "chat" and not capabilities.chat:
        raise ValueError("The selected Provider does not support chat")
    if payload.kind == "embedding" and not capabilities.embeddings:
        raise ValueError("The selected Provider does not support embeddings")
    profile = ProviderProfile(
        kind=payload.kind,
        name=payload.name.strip(),
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model.strip(),
        secret_ref=payload.secret_ref,
        temperature=payload.temperature,
        max_output_tokens=payload.max_output_tokens,
        embedding_dimension=payload.embedding_dimension,
        batch_size=payload.batch_size,
        extra_headers=payload.extra_headers,
        is_active=False,
    )
    session.add(profile)
    session.flush()
    if payload.kind == "embedding":
        session.add(
            EmbeddingIndexVersion(
                embedding_profile_id=profile.id,
                dimension=payload.embedding_dimension,
                status="pending",
            )
        )
        session.flush()
    return profile


def delete_profile(session: Session, profile_id: uuid.UUID) -> bool:
    profile = session.get(ProviderProfile, profile_id)
    if profile is None:
        return False
    if profile.is_active:
        raise ValueError("Active profiles must be replaced before deletion")
    version_ids = (
        session.execute(
            select(EmbeddingIndexVersion.id).where(
                EmbeddingIndexVersion.embedding_profile_id == profile.id
            )
        )
        .scalars()
        .all()
    )
    if version_ids:
        session.execute(
            delete(ChunkEmbedding).where(
                ChunkEmbedding.index_version_id.in_(version_ids)
            )
        )
        session.execute(
            delete(EmbeddingIndexVersion).where(
                EmbeddingIndexVersion.id.in_(version_ids)
            )
        )
    session.delete(profile)
    session.flush()
    provider_runtime_registry.remove(str(profile_id))
    return True


def update_secret_reference(
    session: Session, profile_id: uuid.UUID, secret_ref: str | None
) -> ProviderProfile:
    profile = session.get(ProviderProfile, profile_id)
    if profile is None:
        raise ValueError("Provider profile was not found")
    profile.secret_ref = secret_ref.strip() if secret_ref else None
    profile.config_version += 1
    if not profile.secret_ref:
        profile.is_active = False
        provider_runtime_registry.remove(str(profile.id))
    session.flush()
    return profile


def activate_profile(
    session: Session,
    profile_id: uuid.UUID,
    api_key: str | None,
    *,
    registry: ProviderRuntimeRegistry = provider_runtime_registry,
) -> ProviderProfile:
    profile = session.get(ProviderProfile, profile_id)
    if profile is None:
        raise ValueError("Provider profile was not found")
    version_id: str | None = None
    if profile.kind == "embedding":
        version = (
            session.execute(
                select(EmbeddingIndexVersion)
                .where(EmbeddingIndexVersion.embedding_profile_id == profile.id)
                .where(EmbeddingIndexVersion.status.in_(["ready", "active"]))
                .order_by(EmbeddingIndexVersion.created_at.desc())
            )
            .scalars()
            .first()
        )
        if version is None:
            raise ValueError("Embedding profile must be re-indexed before activation")
        version_id = str(version.id)
        for active_version in session.execute(
            select(EmbeddingIndexVersion).where(
                EmbeddingIndexVersion.status == "active"
            )
        ).scalars():
            active_version.status = "ready"
        version.status = "active"
    payload = profile_to_input(profile, api_key=api_key)
    registry.activate(
        str(profile.id),
        payload,
        api_key,
        embedding_index_version_id=version_id,
    )
    for other in session.execute(
        select(ProviderProfile).where(ProviderProfile.kind == profile.kind)
    ).scalars():
        other.is_active = other.id == profile.id
    session.flush()
    return profile


async def test_provider_connection(
    payload: ProviderConnectionTestRequest,
    *,
    registry: ProviderRuntimeRegistry | None = None,
) -> ProviderConnectionTestResponse:
    entry = get_provider_entry(payload.provider)
    temporary = registry or ProviderRuntimeRegistry()
    profile_id = payload.profile_id or f"test-{uuid.uuid4()}"
    secret = payload.api_key.get_secret_value() if payload.api_key else None
    started = perf_counter()
    try:
        snapshot = temporary.activate(profile_id, payload, secret)
        actual_dimension: int | None = None
        if payload.kind == "chat":
            if snapshot.chat is None:
                raise ValueError("Chat Provider could not be initialized")
            snapshot.chat.generate("Reply with OK.")
            structured = getattr(snapshot.chat, "generate_structured", None)
            if entry.capabilities.structured_output and callable(structured):
                structured('{"task":"Return {\\"ok\\":true}."}')
            if entry.capabilities.streaming:
                stream = snapshot.chat.stream_chat_completion(
                    "Reply with OK.", max_tokens=8
                )
                try:
                    async for chunk in stream:
                        if chunk.delta or chunk.finish_reason:
                            break
                finally:
                    close = getattr(stream, "aclose", None)
                    if callable(close):
                        await close()
        else:
            if snapshot.embedding is None:
                raise ValueError("Embedding Provider could not be initialized")
            vector = snapshot.embedding.embed_text("dimension check")
            actual_dimension = len(vector)
            if actual_dimension != payload.embedding_dimension:
                raise ValueError(
                    "Embedding dimension mismatch: "
                    f"configured {payload.embedding_dimension}, actual {actual_dimension}"
                )
        return ProviderConnectionTestResponse(
            success=True,
            provider=payload.provider,
            model=payload.model,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            capabilities=entry.capabilities,
            actual_embedding_dimension=actual_dimension,
            message="Connection test succeeded.",
        )
    except (ValueError, LLMProviderError, EmbeddingProviderError) as exc:
        return ProviderConnectionTestResponse(
            success=False,
            provider=payload.provider,
            model=payload.model,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            capabilities=entry.capabilities,
            message=_safe_provider_error(exc),
        )


def reindex_embedding_profile(
    session: Session,
    profile_id: uuid.UUID,
    api_key: str | None,
    *,
    registry: ProviderRuntimeRegistry | None = None,
) -> EmbeddingIndexVersion:
    profile = session.get(ProviderProfile, profile_id)
    if profile is None or profile.kind != "embedding":
        raise ValueError("Embedding profile was not found")
    version = (
        session.execute(
            select(EmbeddingIndexVersion)
            .where(EmbeddingIndexVersion.embedding_profile_id == profile.id)
            .where(EmbeddingIndexVersion.status.in_(["pending", "failed"]))
            .order_by(EmbeddingIndexVersion.created_at.desc())
        )
        .scalars()
        .first()
    )
    if version is None:
        version = EmbeddingIndexVersion(
            embedding_profile_id=profile.id,
            dimension=profile.embedding_dimension,
            status="pending",
        )
        session.add(version)
        session.flush()
    temporary = registry or ProviderRuntimeRegistry()
    snapshot = temporary.activate(
        str(profile.id), profile_to_input(profile, api_key=api_key), api_key
    )
    if snapshot.embedding is None:
        raise ValueError("Embedding Provider could not be initialized")
    chunks = (
        session.execute(
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(active_processing_filter())
            .order_by(DocumentChunk.id)
        )
        .scalars()
        .all()
    )
    version.status = "building"
    version.total_chunks = len(chunks)
    version.embedded_chunks = 0
    session.execute(
        delete(ChunkEmbedding).where(ChunkEmbedding.index_version_id == version.id)
    )
    try:
        batch_size = profile.batch_size or 16
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = snapshot.embedding.embed_texts([chunk.content for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                if len(vector) != version.dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {version.dimension}, got {len(vector)}"
                    )
                session.add(
                    ChunkEmbedding(
                        chunk_id=chunk.id,
                        index_version_id=version.id,
                        embedding=vector if version.dimension == 1024 else None,
                        embedding_legacy=vector if version.dimension != 1024 else None,
                    )
                )
            version.embedded_chunks += len(batch)
            session.flush()
        version.status = "ready"
        version.completed_at = datetime.now(UTC)
        for processing_version in session.execute(
            select(PdfProcessingVersion).join(
                Document,
                Document.active_processing_version_id == PdfProcessingVersion.id,
            )
        ).scalars():
            processing_version.text_index_version_id = version.id
        session.flush()
        return version
    except Exception:
        version.status = "failed"
        session.flush()
        raise


def profile_to_input(
    profile: ProviderProfile, *, api_key: str | None = None
) -> ProviderProfileInput:
    return ProviderProfileInput(
        kind=profile.kind,
        name=profile.name,
        provider=profile.provider,
        api_key=api_key,
        secret_ref=profile.secret_ref,
        base_url=profile.base_url,
        model=profile.model,
        temperature=profile.temperature,
        max_output_tokens=profile.max_output_tokens,
        embedding_dimension=profile.embedding_dimension,
        batch_size=profile.batch_size,
        extra_headers=profile.extra_headers or {},
    )


def profile_to_read(profile: ProviderProfile) -> ProviderProfileRead:
    active_runtime = provider_runtime_registry.get_active(profile.kind)
    return ProviderProfileRead(
        id=str(profile.id),
        kind=profile.kind,
        name=profile.name,
        provider=profile.provider,
        base_url=profile.base_url,
        model=profile.model,
        secret_ref=profile.secret_ref,
        api_key_configured=bool(profile.secret_ref),
        api_key_mask="••••••••" if profile.secret_ref else None,
        temperature=profile.temperature,
        max_output_tokens=profile.max_output_tokens,
        embedding_dimension=profile.embedding_dimension,
        batch_size=profile.batch_size,
        extra_headers=profile.extra_headers or {},
        config_version=profile.config_version,
        is_active=profile.is_active,
        runtime_active=bool(
            active_runtime is not None and active_runtime.profile_id == str(profile.id)
        ),
    )


def index_to_read(version: EmbeddingIndexVersion) -> EmbeddingIndexVersionRead:
    return EmbeddingIndexVersionRead(
        id=str(version.id),
        embedding_profile_id=str(version.embedding_profile_id),
        dimension=version.dimension,
        status=version.status,
        total_chunks=version.total_chunks,
        embedded_chunks=version.embedded_chunks,
    )


def _safe_provider_error(error: BaseException) -> str:
    message = str(error)
    if "dimension" in message.lower():
        return message
    if isinstance(error, ValueError):
        return message[:300]
    return f"Provider connection failed ({type(error).__name__})."
