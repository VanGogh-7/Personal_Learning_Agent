import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "d4b7e2a9c6f1_restore_legacy_chunk_uniqueness.py"
)
SPEC = importlib.util.spec_from_file_location("stage64_migration", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _connection():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    connection = engine.connect()
    connection.execute(
        sa.text(
            "CREATE TABLE document_chunks ("
            "id TEXT PRIMARY KEY, "
            "document_id TEXT NOT NULL, "
            "processing_version_id TEXT NULL, "
            "chunk_index INTEGER NOT NULL)"
        )
    )
    return engine, connection


def _run_migration(connection, function) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        function()


def test_stage64_migration_enforces_legacy_uniqueness_and_downgrades() -> None:
    engine, connection = _connection()
    try:
        connection.execute(
            sa.text(
                "INSERT INTO document_chunks VALUES "
                "('legacy-1', 'doc-1', NULL, 0), "
                "('version-1', 'doc-1', 'v1', 0), "
                "('version-2', 'doc-1', 'v2', 0)"
            )
        )
        _run_migration(connection, MIGRATION.upgrade)

        indexes = {
            item["name"]
            for item in sa.inspect(connection).get_indexes("document_chunks")
        }
        assert MIGRATION.INDEX_NAME in indexes
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO document_chunks VALUES "
                    "('legacy-duplicate', 'doc-1', NULL, 0)"
                )
            )

        _run_migration(connection, MIGRATION.downgrade)
        indexes = {
            item["name"]
            for item in sa.inspect(connection).get_indexes("document_chunks")
        }
        assert MIGRATION.INDEX_NAME not in indexes
    finally:
        connection.close()
        engine.dispose()


def test_stage64_migration_refuses_to_delete_existing_duplicates() -> None:
    engine, connection = _connection()
    try:
        connection.execute(
            sa.text(
                "INSERT INTO document_chunks VALUES "
                "('legacy-1', 'doc-1', NULL, 0), "
                "('legacy-2', 'doc-1', NULL, 0)"
            )
        )

        with pytest.raises(RuntimeError, match="Resolve duplicates"):
            _run_migration(connection, MIGRATION.upgrade)
        count = connection.execute(
            sa.text("SELECT COUNT(*) FROM document_chunks")
        ).scalar_one()
        assert count == 2
    finally:
        connection.close()
        engine.dispose()
