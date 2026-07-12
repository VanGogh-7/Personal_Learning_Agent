from contextlib import asynccontextmanager
import json
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.agent_routes import router as agent_router
from app.api.ingestion_routes import router as ingestion_router
from app.api.learning_event_routes import router as learning_event_router
from app.api.library_routes import router as library_router
from app.api.memory_routes import router as memory_router
from app.api.notes_routes import router as notes_router
from app.api.rag_routes import router as rag_router
from app.api.settings_routes import router as settings_router
from app.api.routes import router
from app.core.config import get_settings
from app.memory.checkpointer import checkpointer_manager
from app.mcp.client import mcp_client_manager
from app.providers.http_clients import provider_http_clients

settings = get_settings()
logger = logging.getLogger(__name__)

LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(checkpointer_manager.startup)
    await mcp_client_manager.startup()
    try:
        yield
    finally:
        await mcp_client_manager.shutdown()
        await run_in_threadpool(checkpointer_manager.shutdown)
        await provider_http_clients.aclose()
        await run_in_threadpool(provider_http_clients.close)


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    logger.warning(
        json.dumps(
            {
                "event": "request_validation_failed",
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": 422,
                "error_type": "RequestValidationError",
            },
            separators=(",", ":"),
        )
    )
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"],
)
app.include_router(router)
app.include_router(agent_router)
app.include_router(ingestion_router)
app.include_router(rag_router)
app.include_router(memory_router)
app.include_router(library_router)
app.include_router(notes_router)
app.include_router(learning_event_router)
app.include_router(settings_router)
