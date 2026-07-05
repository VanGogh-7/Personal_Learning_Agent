from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import ROOT_ENV_FILE, Settings, get_database_url, get_settings
from app.db.session import get_engine, get_session_factory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _clear_db_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_settings_has_database_url_field() -> None:
    settings = Settings(_env_file=None)
    assert hasattr(settings, "database_url")


def test_root_env_file_points_to_project_root() -> None:
    assert ROOT_ENV_FILE.name == ".env"
    assert ROOT_ENV_FILE.parent == BACKEND_DIR.parent


def test_settings_reads_database_url_from_env_var(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/testdb")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://user:pass@localhost/testdb"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_get_engine_does_not_require_a_live_connection(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/testdb")
    _clear_db_caches()
    try:
        # Engine creation is lazy: SQLAlchemy only connects when a query is run.
        engine = get_engine()
        assert engine is not None
        assert engine.url.database == "testdb"
    finally:
        _clear_db_caches()


def test_get_database_url_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_database_url()
    finally:
        get_settings.cache_clear()


def test_get_database_url_returns_value_when_set(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/testdb")
    get_settings.cache_clear()
    try:
        assert get_database_url() == "postgresql+psycopg://user:pass@localhost/testdb"
    finally:
        get_settings.cache_clear()


def test_alembic_script_directory_has_initial_revision() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1

    revision = script.get_revision(heads[0])
    assert revision.revision == "ff156aef8dbe"
    assert revision.down_revision is None
