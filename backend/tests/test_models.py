from app.db.base import Base
from app.models import AgentRun, Document, DocumentChunk, LearningSource


def test_all_models_registered_on_metadata() -> None:
    assert set(Base.metadata.tables.keys()) == {
        "learning_sources",
        "documents",
        "document_chunks",
        "agent_runs",
    }


def test_learning_source_columns() -> None:
    table = LearningSource.__table__

    assert set(table.columns.keys()) == {
        "id", "title", "source_type", "description", "author", "url",
        "created_at", "updated_at",
    }
    assert not table.c.title.nullable
    assert not table.c.source_type.nullable
    assert table.c.description.nullable
    assert table.c.author.nullable
    assert table.c.url.nullable


def test_document_columns_and_foreign_key() -> None:
    table = Document.__table__

    assert set(table.columns.keys()) == {
        "id", "source_id", "title", "file_path", "file_type", "content_hash",
        "created_at", "updated_at",
    }
    assert not table.c.title.nullable
    assert not table.c.file_type.nullable
    assert table.c.source_id.nullable

    fk_targets = {fk.target_fullname for fk in table.c.source_id.foreign_keys}
    assert fk_targets == {"learning_sources.id"}


def test_document_chunk_columns_constraints_and_foreign_key() -> None:
    table = DocumentChunk.__table__

    assert set(table.columns.keys()) == {
        "id", "document_id", "chunk_index", "content", "char_start",
        "char_end", "created_at",
    }
    assert not table.c.document_id.nullable
    assert not table.c.content.nullable
    assert not table.c.char_start.nullable
    assert not table.c.char_end.nullable

    fk_targets = {fk.target_fullname for fk in table.c.document_id.foreign_keys}
    assert fk_targets == {"documents.id"}

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "uq_document_chunks_document_id_chunk_index" in constraint_names
    assert "ck_document_chunks_char_start_non_negative" in constraint_names
    assert "ck_document_chunks_char_end_non_negative" in constraint_names
    assert "ck_document_chunks_char_end_gte_char_start" in constraint_names


def test_agent_run_columns() -> None:
    table = AgentRun.__table__

    assert set(table.columns.keys()) == {
        "id", "run_type", "status", "input_text", "output_text",
        "error_message", "created_at", "updated_at",
    }
    assert not table.c.run_type.nullable
    assert not table.c.status.nullable
    assert table.c.input_text.nullable
    assert table.c.output_text.nullable
    assert table.c.error_message.nullable
