from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url


@lru_cache
def get_engine() -> Engine:
    """Create the SQLAlchemy engine.

    Engine creation does not open a connection; SQLAlchemy connects
    lazily on first use. Raises ValueError if DATABASE_URL is not set.
    """
    return create_engine(get_database_url(), future=True)


@lru_cache
def get_session_factory() -> sessionmaker:
    return sessionmaker(
        bind=get_engine(), autocommit=False, autoflush=False, future=True
    )


def get_db_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    return get_session_factory()()
