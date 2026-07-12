from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.embeddings.base import EMBEDDING_DIMENSION
from app.models import (
    AgentRun,
    Conversation,
    ConversationSummary,
    ConversationTurn,
    Document,
    DocumentChunk,
    LearningSource,
    LearningEvent,
    LibraryItem,
    LongTermMemory,
    Note,
)


def test_all_models_registered_on_metadata() -> None:
    assert set(Base.metadata.tables.keys()) == {
        "learning_sources",
        "documents",
        "document_chunks",
        "agent_runs",
        "conversation_turns",
        "conversations",
        "conversation_summaries",
        "long_term_memories",
        "library_items",
        "notes",
        "learning_events",
        "provider_profiles",
        "embedding_index_versions",
        "chunk_embeddings",
        "pdf_processing_versions",
        "document_pages",
        "visual_index_versions",
        "visual_page_embeddings",
    }


def test_learning_source_columns() -> None:
    table = LearningSource.__table__

    assert set(table.columns.keys()) == {
        "id",
        "title",
        "source_type",
        "description",
        "author",
        "url",
        "created_at",
        "updated_at",
    }
    assert not table.c.title.nullable
    assert not table.c.source_type.nullable
    assert table.c.description.nullable
    assert table.c.author.nullable
    assert table.c.url.nullable


def test_document_columns_and_foreign_key() -> None:
    table = Document.__table__

    assert set(table.columns.keys()) == {
        "id",
        "source_id",
        "library_item_id",
        "title",
        "file_path",
        "file_type",
        "content_hash",
        "created_at",
        "updated_at",
        "active_processing_version_id",
    }
    assert not table.c.title.nullable
    assert not table.c.file_type.nullable
    assert table.c.source_id.nullable
    assert table.c.library_item_id.nullable

    fk_targets = {fk.target_fullname for fk in table.c.source_id.foreign_keys}
    assert fk_targets == {"learning_sources.id"}

    library_fk_targets = {
        fk.target_fullname for fk in table.c.library_item_id.foreign_keys
    }
    assert library_fk_targets == {"library_items.id"}

    index_names = {index.name for index in table.indexes}
    assert "ix_documents_library_item_id" in index_names


def test_document_chunk_columns_constraints_and_foreign_key() -> None:
    table = DocumentChunk.__table__

    assert set(table.columns.keys()) == {
        "id",
        "document_id",
        "chunk_index",
        "content",
        "char_start",
        "char_end",
        "page_start",
        "page_end",
        "section_type",
        "chapter_title",
        "section_title",
        "created_at",
        "embedding",
        "processing_version_id",
        "parent_chunk_id",
        "element_type",
        "section_path",
        "bounding_boxes",
        "extraction_method",
        "ocr_confidence",
    }
    assert not table.c.document_id.nullable
    assert not table.c.content.nullable
    assert not table.c.char_start.nullable
    assert not table.c.char_end.nullable
    assert table.c.page_start.nullable
    assert table.c.page_end.nullable
    assert not table.c.section_type.nullable
    assert table.c.chapter_title.nullable
    assert table.c.section_title.nullable

    fk_targets = {fk.target_fullname for fk in table.c.document_id.foreign_keys}
    assert fk_targets == {"documents.id"}

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "uq_document_chunks_document_version_chunk_index" in constraint_names
    assert "ck_document_chunks_char_start_non_negative" in constraint_names
    assert "ck_document_chunks_char_end_non_negative" in constraint_names
    assert "ck_document_chunks_char_end_gte_char_start" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "uq_document_chunks_legacy_document_chunk_index" in index_names


def test_document_chunk_embedding_column_is_nullable_vector() -> None:
    table = DocumentChunk.__table__

    assert table.c.embedding.nullable
    assert isinstance(table.c.embedding.type, Vector)
    assert table.c.embedding.type.dim == EMBEDDING_DIMENSION


def test_conversation_turn_columns_and_constraints() -> None:
    table = ConversationTurn.__table__

    assert set(table.columns.keys()) == {
        "id",
        "session_id",
        "question",
        "answer",
        "turn_index",
        "metadata_json",
        "created_at",
        "conversation_id",
    }
    assert not table.c.session_id.nullable
    assert not table.c.question.nullable
    assert not table.c.answer.nullable
    assert table.c.turn_index.nullable
    assert table.c.metadata_json.nullable

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "ck_conversation_turns_session_id_non_empty" in constraint_names
    assert "ck_conversation_turns_question_non_empty" in constraint_names
    assert "ck_conversation_turns_answer_non_empty" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_conversation_turns_session_id" in index_names
    assert "ix_conversation_turns_conversation_id" in index_names


def test_long_term_memory_columns_and_constraints() -> None:
    table = LongTermMemory.__table__

    assert set(table.columns.keys()) == {
        "id",
        "memory_type",
        "content",
        "importance",
        "source",
        "tags",
        "metadata_json",
        "last_accessed_at",
        "created_at",
        "updated_at",
        "namespace",
        "subject_id",
        "memory_subtype",
        "structured_data",
        "embedding",
        "confidence",
        "status",
        "source_type",
        "source_turn_id",
        "source_event_id",
        "supersedes_id",
        "valid_from",
        "valid_until",
        "access_count",
    }
    assert not table.c.memory_type.nullable
    assert not table.c.content.nullable
    assert not table.c.importance.nullable
    assert table.c.source.nullable
    assert table.c.tags.nullable
    assert table.c.metadata_json.nullable
    assert table.c.last_accessed_at.nullable

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "ck_long_term_memories_memory_type_non_empty" in constraint_names
    assert "ck_long_term_memories_content_non_empty" in constraint_names
    assert "ck_long_term_memories_importance_range" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_long_term_memories_memory_type" in index_names
    assert "ix_long_term_memories_importance" in index_names
    assert "ix_long_term_memories_created_at" in index_names
    assert "ix_long_term_memories_namespace_status" in index_names
    assert "ix_long_term_memories_type_subtype" in index_names


def test_conversation_and_summary_models() -> None:
    conversation = Conversation.__table__
    assert set(conversation.columns.keys()) == {
        "id",
        "thread_id",
        "namespace",
        "subject_id",
        "legacy_session_id",
        "created_at",
        "updated_at",
    }
    assert not conversation.c.thread_id.nullable
    assert not conversation.c.namespace.nullable

    summary = ConversationSummary.__table__
    assert set(summary.columns.keys()) == {
        "id",
        "conversation_id",
        "summary",
        "covered_until_turn_id",
        "source_turn_count",
        "version",
        "created_at",
        "updated_at",
    }
    assert {fk.target_fullname for fk in summary.c.conversation_id.foreign_keys} == {
        "conversations.id"
    }


def test_library_item_columns_and_constraints() -> None:
    table = LibraryItem.__table__

    assert set(table.columns.keys()) == {
        "id",
        "title",
        "author",
        "description",
        "file_path",
        "file_type",
        "topic_tags",
        "status",
        "created_at",
        "updated_at",
    }
    assert not table.c.title.nullable
    assert table.c.author.nullable
    assert table.c.description.nullable
    assert table.c.file_path.nullable
    assert table.c.file_type.nullable
    assert table.c.topic_tags.nullable
    assert not table.c.status.nullable

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "ck_library_items_title_non_empty" in constraint_names
    assert "ck_library_items_status_non_empty" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_library_items_title" in index_names
    assert "ix_library_items_status" in index_names
    assert "ix_library_items_created_at" in index_names


def test_note_columns_constraints_indexes_and_foreign_key() -> None:
    table = Note.__table__

    assert set(table.columns.keys()) == {
        "id",
        "title",
        "content_latex",
        "description",
        "library_item_id",
        "source_session_id",
        "topic_tags",
        "status",
        "created_at",
        "updated_at",
    }
    assert not table.c.title.nullable
    assert not table.c.content_latex.nullable
    assert table.c.description.nullable
    assert table.c.library_item_id.nullable
    assert table.c.source_session_id.nullable
    assert table.c.topic_tags.nullable
    assert not table.c.status.nullable

    fk_targets = {fk.target_fullname for fk in table.c.library_item_id.foreign_keys}
    assert fk_targets == {"library_items.id"}

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "ck_notes_title_non_empty" in constraint_names
    assert "ck_notes_content_latex_required" in constraint_names
    assert "ck_notes_status_non_empty" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_notes_library_item_id" in index_names
    assert "ix_notes_status" in index_names
    assert "ix_notes_created_at" in index_names


def test_learning_event_columns_constraints_indexes_and_foreign_keys() -> None:
    table = LearningEvent.__table__

    assert set(table.columns.keys()) == {
        "id",
        "event_type",
        "title",
        "description",
        "source_type",
        "source_id",
        "library_item_id",
        "note_id",
        "session_id",
        "metadata_json",
        "created_at",
    }
    assert not table.c.event_type.nullable
    assert not table.c.title.nullable
    assert table.c.description.nullable
    assert table.c.source_type.nullable
    assert table.c.source_id.nullable
    assert table.c.library_item_id.nullable
    assert table.c.note_id.nullable
    assert table.c.session_id.nullable
    assert table.c.metadata_json.nullable
    assert not table.c.created_at.nullable

    library_fk_targets = {
        fk.target_fullname for fk in table.c.library_item_id.foreign_keys
    }
    assert library_fk_targets == {"library_items.id"}
    note_fk_targets = {fk.target_fullname for fk in table.c.note_id.foreign_keys}
    assert note_fk_targets == {"notes.id"}

    constraint_names = {c.name for c in table.constraints if c.name}
    assert "ck_learning_events_event_type_non_empty" in constraint_names
    assert "ck_learning_events_title_non_empty" in constraint_names

    index_names = {index.name for index in table.indexes}
    assert "ix_learning_events_event_type" in index_names
    assert "ix_learning_events_source_type" in index_names
    assert "ix_learning_events_source_id" in index_names
    assert "ix_learning_events_library_item_id" in index_names
    assert "ix_learning_events_note_id" in index_names
    assert "ix_learning_events_session_id" in index_names
    assert "ix_learning_events_created_at" in index_names


def test_agent_run_columns() -> None:
    table = AgentRun.__table__

    assert set(table.columns.keys()) == {
        "id",
        "run_type",
        "status",
        "input_text",
        "output_text",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert not table.c.run_type.nullable
    assert not table.c.status.nullable
    assert table.c.input_text.nullable
    assert table.c.output_text.nullable
    assert table.c.error_message.nullable
