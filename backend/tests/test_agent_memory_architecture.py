import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.memory.context_builder as context_builder_module
from app.core.config import get_settings
from app.embeddings.mock import MockEmbeddingProvider
from app.memory.consolidation import consolidate_candidate
from app.memory.context_builder import (
    build_memory_context,
    render_untrusted_memory_context,
)
from app.memory.conversations import resolve_conversation
from app.memory.extraction import ConservativeMemoryCandidateExtractor, MemoryCandidate
from app.memory.models import MemoryAction, MemoryStatus, MemorySubtype, MemoryType
from app.memory.repository import soft_delete_memory
from app.memory.retrieval import retrieve_memories
from app.memory.short_term import get_recent_effective_turns, save_turn
from app.memory.summary import (
    get_conversation_summary,
    update_rolling_summary_if_needed,
)
from app.models.conversation import Conversation
from app.models.conversation_summary import ConversationSummary
from app.models.conversation_turn import ConversationTurn
from app.models.long_term_memory import LongTermMemory


@pytest.fixture
def memory_architecture_session():
    engine = create_engine("sqlite:///:memory:")
    Conversation.metadata.create_all(
        engine,
        tables=[
            Conversation.__table__,
            ConversationTurn.__table__,
            ConversationSummary.__table__,
            LongTermMemory.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _preference(language: str = "Python", *, explicit: bool = True) -> MemoryCandidate:
    return MemoryCandidate(
        memory_type=MemoryType.SEMANTIC,
        memory_subtype=MemorySubtype.USER_PREFERENCE,
        content=f"User prefers {language} for LeetCode.",
        structured_data={
            "subject": "user",
            "predicate": "preferred_leetcode_language",
            "object": language,
            "scope": "leetcode",
        },
        importance=0.9,
        confidence=0.95,
        durability=0.9,
        scope="leetcode",
        sensitive=False,
        explicit=explicit,
    )


def test_memory_candidate_rejects_type_subtype_mismatch() -> None:
    with pytest.raises(ValidationError):
        MemoryCandidate(
            memory_type=MemoryType.EPISODIC,
            memory_subtype=MemorySubtype.USER_PREFERENCE,
            content="invalid",
            importance=0.9,
            confidence=0.9,
            durability=0.9,
        )


def test_conservative_extraction_accepts_stable_preference_and_rejects_temporary() -> (
    None
):
    extractor = ConservativeMemoryCandidateExtractor()
    candidates = extractor.extract("以后给我讲数学定理时，先从定义开始。")
    assert len(candidates) == 1
    assert candidates[0].memory_type == MemoryType.SEMANTIC
    assert candidates[0].memory_subtype == MemorySubtype.USER_PREFERENCE
    assert extractor.extract("我今天有点困。") == []
    assert extractor.extract("这本数学书里的闭图定理是什么？") == []


def test_automatic_write_threshold_can_ignore_low_quality(
    memory_architecture_session,
) -> None:
    candidate = _preference(explicit=False).model_copy(
        update={"importance": 0.2, "confidence": 0.2, "durability": 0.2}
    )
    result = consolidate_candidate(
        memory_architecture_session,
        namespace="user-a",
        candidate=candidate,
        embedding_provider=MockEmbeddingProvider(),
    )
    assert result.action == MemoryAction.IGNORE


def test_consolidation_create_update_supersede_and_ignore(
    memory_architecture_session,
) -> None:
    provider = MockEmbeddingProvider()
    created = consolidate_candidate(
        memory_architecture_session,
        namespace="user-a",
        candidate=_preference("Python"),
        embedding_provider=provider,
    )
    updated = consolidate_candidate(
        memory_architecture_session,
        namespace="user-a",
        candidate=_preference("Python"),
        embedding_provider=provider,
    )
    superseded = consolidate_candidate(
        memory_architecture_session,
        namespace="user-a",
        candidate=_preference("Rust"),
        embedding_provider=provider,
    )

    assert created.action == MemoryAction.CREATE
    assert updated.action == MemoryAction.UPDATE
    assert updated.memory_id == created.memory_id
    assert superseded.action == MemoryAction.SUPERSEDE
    old = memory_architecture_session.get(LongTermMemory, created.memory_id)
    new = memory_architecture_session.get(LongTermMemory, superseded.memory_id)
    assert old.status == MemoryStatus.SUPERSEDED
    assert new.status == MemoryStatus.ACTIVE
    assert new.supersedes_id == old.id


def test_retrieval_is_namespace_isolated_and_active_only(
    memory_architecture_session,
) -> None:
    provider = MockEmbeddingProvider()
    for namespace, language in (("user-a", "Rust"), ("user-b", "Python")):
        consolidate_candidate(
            memory_architecture_session,
            namespace=namespace,
            candidate=_preference(language),
            embedding_provider=provider,
        )
    results = retrieve_memories(
        memory_architecture_session,
        namespace="user-a",
        query="Which language should I use for LeetCode?",
        predicate="preferred_leetcode_language",
        scope="leetcode",
        embedding_provider=provider,
    )
    assert len(results) == 1
    assert "Rust" in results[0].content

    assert soft_delete_memory(memory_architecture_session, results[0].id)
    assert (
        retrieve_memories(
            memory_architecture_session,
            namespace="user-a",
            query="LeetCode language",
            embedding_provider=provider,
        )
        == []
    )


def test_recent_turn_window_and_rolling_summary_do_not_cross_conversations(
    memory_architecture_session, monkeypatch
) -> None:
    monkeypatch.setenv("MEMORY_RECENT_TURN_LIMIT", "2")
    monkeypatch.setenv("MEMORY_SUMMARY_TRIGGER_TURNS", "3")
    get_settings.cache_clear()
    try:
        first = resolve_conversation(
            memory_architecture_session, legacy_session_id="first"
        )
        second = resolve_conversation(
            memory_architecture_session, legacy_session_id="second"
        )
        for index in range(4):
            save_turn(
                memory_architecture_session,
                first.session_id,
                f"Q{index}",
                f"A{index}",
                conversation_id=first.conversation_id,
            )
        save_turn(
            memory_architecture_session,
            second.session_id,
            "Other Q",
            "Other A",
            conversation_id=second.conversation_id,
        )
        recent = get_recent_effective_turns(
            memory_architecture_session, first.conversation_id, limit=2
        )
        assert [turn.question for turn in recent] == ["Q2", "Q3"]

        summary = update_rolling_summary_if_needed(
            memory_architecture_session, conversation_id=first.conversation_id
        )
        assert summary.updated is True
        assert "Q0" in summary.summary and "Q1" in summary.summary
        assert "Other Q" not in summary.summary
        persisted = get_conversation_summary(
            memory_architecture_session, first.conversation_id
        )
        assert persisted.source_turn_count == 2

        second_update = update_rolling_summary_if_needed(
            memory_architecture_session, conversation_id=first.conversation_id
        )
        assert second_update.updated is False
    finally:
        get_settings.cache_clear()


def test_context_construction_separates_memory_summary_and_recent_turns(
    memory_architecture_session,
) -> None:
    identity = resolve_conversation(memory_architecture_session)
    save_turn(
        memory_architecture_session,
        identity.session_id,
        "Earlier question",
        "Earlier answer",
        conversation_id=identity.conversation_id,
    )
    consolidate_candidate(
        memory_architecture_session,
        namespace=identity.namespace,
        candidate=_preference("Rust"),
        embedding_provider=MockEmbeddingProvider(),
    )
    context = build_memory_context(
        memory_architecture_session,
        conversation_id=identity.conversation_id,
        namespace=identity.namespace,
        query="LeetCode language",
    )
    rendered = render_untrusted_memory_context(context)
    assert "User memory:" in rendered
    assert "Recent messages:" in rendered
    assert "not evidence" in rendered


def test_short_term_context_failure_is_logged_and_not_silently_dropped(
    memory_architecture_session, monkeypatch, caplog
) -> None:
    identity = resolve_conversation(memory_architecture_session)
    monkeypatch.setattr(
        context_builder_module,
        "get_recent_effective_turns",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed")),
    )

    with pytest.raises(RuntimeError, match="failed"):
        build_memory_context(
            memory_architecture_session,
            conversation_id=identity.conversation_id,
            namespace=identity.namespace,
            query="What did we discuss?",
        )
    assert any(
        "conversation_context_load_failed" in record.message
        for record in caplog.records
    )


def test_same_legacy_conversation_reuses_hidden_thread(
    memory_architecture_session,
) -> None:
    first = resolve_conversation(
        memory_architecture_session, legacy_session_id="stable"
    )
    second = resolve_conversation(
        memory_architecture_session, legacy_session_id="stable"
    )
    other = resolve_conversation(memory_architecture_session, legacy_session_id="other")
    assert first.conversation_id == second.conversation_id
    assert first.thread_id == second.thread_id
    assert other.thread_id != first.thread_id
    assert memory_architecture_session.execute(select(Conversation)).scalars().all()
