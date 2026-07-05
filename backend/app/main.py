from fastapi import FastAPI

from app.api.ingestion_routes import router as ingestion_router
from app.api.rag_routes import router as rag_router
from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(router)
app.include_router(ingestion_router)
app.include_router(rag_router)
