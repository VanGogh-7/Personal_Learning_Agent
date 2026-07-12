import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.settings.catalog import list_provider_catalog
from app.settings.schemas import (
    EmbeddingReindexResponse,
    ProviderActivationRequest,
    ProviderCatalogEntry,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResponse,
    ProviderProfileInput,
    ProviderProfileList,
    ProviderProfileRead,
    ProviderSecretReferenceUpdate,
)
from app.settings.service import (
    activate_profile,
    create_profile,
    delete_profile,
    index_to_read,
    list_profiles,
    profile_to_read,
    reindex_embedding_profile,
    test_provider_connection,
    update_secret_reference,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/provider-catalog", response_model=list[ProviderCatalogEntry])
def provider_catalog_endpoint() -> list[ProviderCatalogEntry]:
    return list_provider_catalog()


@router.get("/profiles", response_model=ProviderProfileList)
def list_profiles_endpoint() -> ProviderProfileList:
    session = _session()
    try:
        return list_profiles(session)
    finally:
        session.close()


@router.post("/profiles", response_model=ProviderProfileRead)
def create_profile_endpoint(payload: ProviderProfileInput) -> ProviderProfileRead:
    session = _session()
    try:
        profile = create_profile(session, payload)
        session.commit()
        return profile_to_read(profile)
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        raise _safe_http_error(exc) from exc
    finally:
        session.close()


@router.post("/profiles/{profile_id}/activate", response_model=ProviderProfileRead)
def activate_profile_endpoint(
    profile_id: uuid.UUID, payload: ProviderActivationRequest
) -> ProviderProfileRead:
    session = _session()
    try:
        secret = payload.api_key.get_secret_value() if payload.api_key else None
        profile = activate_profile(session, profile_id, secret)
        session.commit()
        return profile_to_read(profile)
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        raise _safe_http_error(exc) from exc
    finally:
        session.close()


@router.patch("/profiles/{profile_id}/secret", response_model=ProviderProfileRead)
def update_profile_secret_endpoint(
    profile_id: uuid.UUID, payload: ProviderSecretReferenceUpdate
) -> ProviderProfileRead:
    session = _session()
    try:
        profile = update_secret_reference(session, profile_id, payload.secret_ref)
        session.commit()
        return profile_to_read(profile)
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        raise _safe_http_error(exc) from exc
    finally:
        session.close()


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile_endpoint(profile_id: uuid.UUID) -> None:
    session = _session()
    try:
        if not delete_profile(session, profile_id):
            raise HTTPException(
                status_code=404, detail="Provider profile was not found"
            )
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        raise _safe_http_error(exc) from exc
    finally:
        session.close()


@router.post("/test-provider", response_model=ProviderConnectionTestResponse)
async def test_provider_endpoint(
    payload: ProviderConnectionTestRequest,
) -> ProviderConnectionTestResponse:
    return await test_provider_connection(payload)


@router.post("/profiles/{profile_id}/reindex", response_model=EmbeddingReindexResponse)
def reindex_profile_endpoint(
    profile_id: uuid.UUID, payload: ProviderActivationRequest
) -> EmbeddingReindexResponse:
    session = _session()
    try:
        secret = payload.api_key.get_secret_value() if payload.api_key else None
        version = reindex_embedding_profile(session, profile_id, secret)
        session.commit()
        return EmbeddingReindexResponse(
            index_version=index_to_read(version),
            requires_reindex=False,
            message="Re-indexing completed. Activate this profile to use the new vector space.",
        )
    except (ValueError, SQLAlchemyError) as exc:
        session.rollback()
        raise _safe_http_error(exc) from exc
    finally:
        session.close()


def _session():
    try:
        return get_db_session()
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="Settings database is unavailable"
        ) from exc


def _safe_http_error(error: BaseException) -> HTTPException:
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error)[:300])
    return HTTPException(status_code=503, detail="Settings database operation failed")
