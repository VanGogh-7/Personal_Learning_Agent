from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status")
def status() -> dict[str, str]:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
    }
