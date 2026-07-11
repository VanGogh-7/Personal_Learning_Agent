import logging
from threading import RLock
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import get_database_url, get_settings

logger = logging.getLogger(__name__)


class CheckpointerConfigurationError(ValueError):
    """Raised when the configured checkpoint backend is invalid."""


class CheckpointerManager:
    """Own the process-wide LangGraph checkpointer and PostgreSQL pool."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._checkpointer: Any | None = None
        self._pool: Any | None = None
        self._backend: str | None = None

    def startup(self) -> None:
        with self._lock:
            if self._checkpointer is not None:
                return
            backend = get_settings().memory_checkpointer_backend.strip().lower()
            if backend == "memory":
                self._checkpointer = InMemorySaver()
                self._backend = backend
                logger.info("memory_checkpointer_started backend=memory")
                return
            if backend != "postgres":
                raise CheckpointerConfigurationError(
                    "MEMORY_CHECKPOINTER_BACKEND must be postgres or memory"
                )

            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            settings = get_settings()
            conninfo = _to_psycopg_conninfo(get_database_url())
            pool = ConnectionPool(
                conninfo=conninfo,
                min_size=settings.memory_postgres_pool_min_size,
                max_size=settings.memory_postgres_pool_max_size,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                open=False,
            )
            pool.open(wait=True)
            saver = PostgresSaver(pool)
            saver.setup()
            self._pool = pool
            self._checkpointer = saver
            self._backend = backend
            logger.info("memory_checkpointer_started backend=postgres")

    def shutdown(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
            self._pool = None
            self._checkpointer = None
            self._backend = None

    def get(self) -> Any:
        if self._checkpointer is None:
            self.startup()
        return self._checkpointer

    @property
    def backend(self) -> str | None:
        return self._backend


def _to_psycopg_conninfo(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


checkpointer_manager = CheckpointerManager()
