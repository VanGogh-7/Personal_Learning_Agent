from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_routes import router as agent_router
from app.api.ingestion_routes import router as ingestion_router
from app.api.learning_event_routes import router as learning_event_router
from app.api.library_routes import router as library_router
from app.api.memory_routes import router as memory_router
from app.api.notes_routes import router as notes_router
from app.api.rag_routes import router as rag_router
from app.api.routes import router
from app.core.config import get_settings
from app.memory.checkpointer import checkpointer_manager

settings = get_settings()

LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(checkpointer_manager.startup)
    try:
        yield
    finally:
        await run_in_threadpool(checkpointer_manager.shutdown)


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
app.include_router(agent_router)
app.include_router(ingestion_router)
app.include_router(rag_router)
app.include_router(memory_router)
app.include_router(library_router)
app.include_router(notes_router)
app.include_router(learning_event_router)
