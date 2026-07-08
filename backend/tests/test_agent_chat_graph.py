import socket
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.agent_routes as agent_routes_module
import app.graphs.chat_rag_graph as chat_rag_graph_module
from app.api.agent_routes import agent_chat_endpoint
from app.main import app
from app.embeddings.mock import MockEmbeddingProvider
from app.embeddings.providers import EmbeddingProviderError
from app.graphs.schemas import AgentChatRequest
from app.learning_events.constants import EVENT_AGENT_CHAT_QUESTION_ASKED
from app.library.service import create_library_item
from app.llm.providers import LLMConfigurationError
from app.models.conversation_turn import ConversationTurn
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
from app.rag.retrieval import RetrievedChunkResult


client = TestClient(app)


@pytest.fixture
def agent_chat_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    LibraryItem.metadata.create_all(
        engine,
        tables=[
            LibraryItem.__table__,
            Note.__table__,
            Document.__table__,
            DocumentChunk.__table__,
            ConversationTurn.__table__,
            LearningEvent.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    close_session = session.close
    session.close = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(agent_routes_module, "get_db_session", lambda: session)
    try:
        yield session
    finally:
        close_session()
        engine.dispose()


def _create_indexed_item(
    session: Session,
    title: str,
    content: str,
    *,
    page_start: int | None = None,
    page_end: int | None = None,
    section_type: str = "body",
    chapter_title: str | None = None,
    section_title: str | None = None,
) -> LibraryItem:
    item_result = create_library_item(
        session,
        title=title,
        author="Author",
        file_type="txt",
        status="indexed",
    )
    document = Document(
        library_item_id=item_result.item_id,
        title=title,
        file_type="txt",
        file_path=f"/tmp/{title}.txt",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content=content,
            char_start=0,
            char_end=len(content),
            page_start=page_start,
            page_end=page_end,
            section_type=section_type,
            chapter_title=chapter_title,
            section_title=section_title,
            embedding=MockEmbeddingProvider().embed_text(content),
        )
    )
    session.flush()
    item = session.get(LibraryItem, item_result.item_id)
    assert item is not None
    return item


def test_agent_chat_global_scope_works(monkeypatch, agent_chat_session) -> None:
    library_item_id = uuid.uuid4()
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Global Notes",
        document_source_path="/tmp/global.txt",
        library_item_id=library_item_id,
        library_title="Global Book",
        library_author="Global Author",
        chunk_index=0,
        content="Global graph retrieval works.",
        char_start=0,
        char_end=29,
        page_start=3,
        page_end=3,
        score=0.01,
    )
    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: [chunk],
    )

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What does the global graph know?",
            scope_type="global",
            session_id="global-session",
        )
    )

    assert response.scope_type == "global"
    assert response.selected_library_items == []
    assert response.total_retrieved == 1
    assert response.citations[0].citation_id == "S1"
    assert response.citations[0].library_item_id == str(library_item_id)
    assert response.citations[0].page_number == 3
    assert response.retrieved_chunks[0].page_start == 3
    assert response.retrieved_chunks[0].citation == response.citations[0]
    assert response.memory.saved_current_turn is True

    turn = agent_chat_session.execute(select(ConversationTurn)).scalar_one()
    assert turn.metadata_json == {
        "query_type": "agent_chat",
        "scope_type": "global",
        "retrieved_chunk_ids": [str(chunk.chunk_id)],
        "citation_count": 1,
    }

    event = agent_chat_session.execute(select(LearningEvent)).scalar_one()
    assert event.event_type == EVENT_AGENT_CHAT_QUESTION_ASKED
    assert event.session_id == "global-session"
    assert event.metadata_json["scope_type"] == "global"
    assert event.metadata_json["total_retrieved"] == 1


def test_agent_chat_http_endpoint_works(monkeypatch, agent_chat_session) -> None:
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Global Notes",
        document_source_path="/tmp/global.txt",
        chunk_index=0,
        content="HTTP agent chat route works.",
        char_start=0,
        char_end=28,
        score=0.01,
    )
    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: [chunk],
    )

    response = client.post(
        "/api/agent/chat",
        json={
            "question": "Does the agent endpoint work?",
            "scope_type": "global",
            "session_id": "http-session",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope_type"] == "global"
    assert data["route"] == "both"
    assert data["total_retrieved"] == 1
    assert data["citations"][0]["citation_id"] == "S1"
    assert data["web_sources"][0]["source_id"] == "W1"


def test_agent_chat_product_request_message_only_uses_defaults(
    monkeypatch, agent_chat_session
) -> None:
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Global Notes",
        document_source_path="/tmp/global.txt",
        chunk_index=0,
        content="Product message request works without debug fields.",
        char_start=0,
        char_end=50,
        page_start=2,
        page_end=2,
        score=0.01,
    )
    captured: dict[str, int] = {}

    def fake_retrieve(session, question, top_k):
        captured["top_k"] = top_k
        return [chunk]

    monkeypatch.setattr(chat_rag_graph_module, "retrieve_relevant_chunks", fake_retrieve)

    response = agent_chat_endpoint(AgentChatRequest(message="Explain this library topic."))

    assert response.scope_type == "global"
    assert response.session_id
    assert captured["top_k"] == 5
    assert response.total_retrieved == 1
    assert response.citations[0].citation_id == "S1"
    assert response.citations[0].page_number == 2
    assert response.memory.used_long_term_memories == 0


def test_agent_chat_product_selected_library_item_prefers_local_rag(
    agent_chat_session,
) -> None:
    selected = _create_indexed_item(
        agent_chat_session,
        "Analysis",
        "A Banach space is a complete normed vector space.",
        page_start=42,
        page_end=43,
        chapter_title="II Convergence",
        section_title="II.6 Completeness",
    )
    other = _create_indexed_item(
        agent_chat_session,
        "Botany",
        "Plants convert sunlight into chemical energy.",
    )
    selected_id = selected.id
    other_id = other.id

    response = agent_chat_endpoint(
        AgentChatRequest(
            message="What does this book say about Banach spaces?",
            selected_library_item_id=str(selected_id),
        )
    )

    assert response.scope_type == "single_book"
    assert response.route == "local_only"
    assert response.selected_library_items[0].id == str(selected_id)
    assert response.total_retrieved == 1
    assert response.web_sources == []
    assert response.citations[0].citation_id == "S1"
    assert response.citations[0].library_item_id == str(selected_id)
    assert response.citations[0].page_start == 42
    assert response.citations[0].page_end == 43
    assert response.citations[0].chapter_title == "II Convergence"
    assert response.citations[0].section_title == "II.6 Completeness"
    assert response.retrieved_chunks[0].citation == response.citations[0]

    other_document_ids = {
        str(document.id)
        for document in agent_chat_session.execute(
            select(Document).where(Document.library_item_id == other_id)
        ).scalars()
    }
    assert response.retrieved_chunks[0].document_id not in other_document_ids


def test_agent_chat_product_selected_library_items_infers_multi_book_scope(
    agent_chat_session,
) -> None:
    selected_a = _create_indexed_item(
        agent_chat_session,
        "Linear Algebra",
        "Vector spaces have bases.",
    )
    selected_b = _create_indexed_item(
        agent_chat_session,
        "Functional Analysis",
        "Banach spaces are complete.",
    )

    request = AgentChatRequest(
        message="What do these PDFs say about spaces?",
        selected_library_item_ids=[str(selected_a.id), str(selected_a.id), str(selected_b.id)],
    )
    response = agent_chat_endpoint(request)

    assert request.scope_type == "multi_book"
    assert request.library_item_ids == [str(selected_a.id), str(selected_b.id)]
    assert response.scope_type == "multi_book"
    assert response.route == "local_only"
    assert [item.id for item in response.selected_library_items] == [
        str(selected_a.id),
        str(selected_b.id),
    ]
    assert [citation.citation_id for citation in response.citations] == ["S1", "S2"]


def test_agent_chat_web_only_route_skips_local_retrieval(
    monkeypatch, agent_chat_session
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("web_only route should not retrieve local chunks")

    monkeypatch.setattr(chat_rag_graph_module, "retrieve_relevant_chunks", fail_if_called)

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What is the latest news about calculus?",
            scope_type="global",
            session_id="web-session",
        )
    )

    assert response.scope_type == "global"
    assert response.route == "web_only"
    assert response.selected_library_items == []
    assert response.retrieved_chunks == []
    assert response.citations == []
    assert response.total_retrieved == 0
    assert response.local_summary is None
    assert response.web_summary is not None
    assert response.web_sources[0].source_id == "W1"
    assert "No live network request was made" in response.answer
    assert response.memory.saved_current_turn is True


def test_agent_chat_both_route_returns_local_citations_and_web_sources(
    monkeypatch, agent_chat_session
) -> None:
    library_item_id = uuid.uuid4()
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Learning PDF",
        document_source_path="/tmp/learning.pdf",
        library_item_id=library_item_id,
        library_title="Learning Book",
        library_author="Author",
        chunk_index=0,
        content="Derivatives measure local rates of change.",
        char_start=0,
        char_end=42,
        page_start=8,
        page_end=8,
        score=0.02,
    )
    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: [chunk],
    )

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="Explain derivatives",
            scope_type="global",
            session_id="both-session",
        )
    )

    assert response.route == "both"
    assert response.scope_type == "global"
    assert response.total_retrieved == 1
    assert response.citations[0].page_number == 8
    assert response.retrieved_chunks[0].citation == response.citations[0]
    assert response.web_sources[0].provider == "deterministic"
    assert response.local_summary is not None
    assert response.web_summary is not None
    assert "Web research:" in response.answer


def test_agent_chat_synthesis_uses_configured_llm_provider(
    monkeypatch, agent_chat_session
) -> None:
    prompts: list[str] = []

    class RecordingProvider:
        def generate(self, prompt: str) -> str:
            prompts.append(prompt)
            return "Mocked provider synthesis."

    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: [],
    )
    monkeypatch.setattr(
        chat_rag_graph_module,
        "get_llm_provider",
        lambda: RecordingProvider(),
    )

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="Explain derivatives",
            scope_type="global",
            session_id="provider-session",
        )
    )

    assert response.answer == "Mocked provider synthesis."
    assert response.route == "both"
    assert prompts
    assert "Local Library Agent summary:" in prompts[0]
    assert "Web Research Agent summary:" in prompts[0]


def test_agent_chat_provider_configuration_error_is_clean(
    monkeypatch, agent_chat_session
) -> None:
    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: [],
    )
    monkeypatch.setattr(
        chat_rag_graph_module,
        "get_llm_provider",
        lambda: (_ for _ in ()).throw(
            LLMConfigurationError("LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY.")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(
                question="Explain derivatives",
                scope_type="global",
                session_id="provider-error-session",
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY."


def test_agent_chat_embedding_provider_error_is_clean(
    monkeypatch, agent_chat_session
) -> None:
    monkeypatch.setattr(
        chat_rag_graph_module,
        "retrieve_relevant_chunks",
        lambda session, question, top_k: (_ for _ in ()).throw(
            EmbeddingProviderError("Zhipu embedding provider request failed.")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(
                message="Explain derivatives",
                session_id="embedding-error-session",
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Zhipu embedding provider request failed."


def test_agent_chat_single_book_scope_returns_only_selected_chunks(
    agent_chat_session,
) -> None:
    selected = _create_indexed_item(
        agent_chat_session,
        "Topology",
        "Compact spaces have finite subcovers in topology.",
    )
    other = _create_indexed_item(
        agent_chat_session,
        "Algebra",
        "Groups and fields are algebraic structures.",
    )
    selected_id = selected.id
    other_id = other.id

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What is compactness?",
            scope_type="single_book",
            library_item_id=str(selected_id),
            top_k=5,
            session_id="single-session",
        )
    )

    assert response.scope_type == "single_book"
    assert [item.id for item in response.selected_library_items] == [str(selected_id)]
    assert response.selected_library_items[0].title == "Topology"
    assert response.total_retrieved == 1
    assert response.citations[0].library_item_id == str(selected_id)
    assert response.citations[0].library_title == "Topology"
    assert "Compact spaces" in response.retrieved_chunks[0].content

    other_document_ids = {
        str(document.id)
        for document in agent_chat_session.execute(
            select(Document).where(Document.library_item_id == other_id)
        ).scalars()
    }
    assert response.retrieved_chunks[0].document_id not in other_document_ids


def test_agent_chat_multi_book_scope_returns_only_selected_chunks(
    agent_chat_session,
) -> None:
    selected_a = _create_indexed_item(
        agent_chat_session,
        "Linear Algebra",
        "Vector spaces have bases and dimensions.",
    )
    selected_b = _create_indexed_item(
        agent_chat_session,
        "Functional Analysis",
        "Normed spaces have operators and limits.",
    )
    unselected = _create_indexed_item(
        agent_chat_session,
        "Botany",
        "Plants perform photosynthesis.",
    )
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id
    unselected_id = unselected.id

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What do the selected materials say about spaces?",
            scope_type="multi_book",
            library_item_ids=[str(selected_a_id), str(selected_b_id)],
            top_k=5,
            session_id="multi-session",
        )
    )

    returned_library_ids = {
        citation.library_item_id for citation in response.citations
    }
    assert response.scope_type == "multi_book"
    assert returned_library_ids == {str(selected_a_id), str(selected_b_id)}
    assert str(unselected_id) not in returned_library_ids
    assert [item.id for item in response.selected_library_items] == [
        str(selected_a_id),
        str(selected_b_id),
    ]
    assert all(chunk.citation.library_item_id in returned_library_ids for chunk in response.retrieved_chunks)

    events = agent_chat_session.execute(select(LearningEvent)).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == EVENT_AGENT_CHAT_QUESTION_ASKED
    assert events[0].metadata_json["scope_type"] == "multi_book"
    assert events[0].metadata_json["library_item_ids"] == [
        str(selected_a_id),
        str(selected_b_id),
    ]


def test_agent_chat_multi_book_deduplicates_library_item_ids(agent_chat_session) -> None:
    selected_a = _create_indexed_item(agent_chat_session, "Algebra", "Groups have operations.")
    selected_b = _create_indexed_item(agent_chat_session, "Geometry", "Triangles have angles.")
    selected_a_id = selected_a.id
    selected_b_id = selected_b.id

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What is covered?",
            scope_type="multi_book",
            library_item_ids=[str(selected_a_id), str(selected_a_id), str(selected_b_id)],
        )
    )

    assert [item.id for item in response.selected_library_items] == [
        str(selected_a_id),
        str(selected_b_id),
    ]


def test_agent_chat_uses_deterministic_provider_without_network(
    monkeypatch, agent_chat_session
) -> None:
    selected = _create_indexed_item(agent_chat_session, "Analysis", "Limits converge.")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("agent chat deterministic flow must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    response = agent_chat_endpoint(
        AgentChatRequest(
            question="What does analysis say?",
            scope_type="single_book",
            library_item_id=str(selected.id),
        )
    )

    assert "minimal MVP answer" in response.answer


def test_agent_chat_rejects_invalid_scope_type() -> None:
    with pytest.raises(ValidationError):
        AgentChatRequest.model_validate(
            {"question": "Valid question", "scope_type": "planner"}
        )


def test_agent_chat_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        AgentChatRequest(question="   ", scope_type="global")


def test_agent_chat_product_request_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        AgentChatRequest(message="   ")


def test_agent_chat_rejects_missing_single_book_id(agent_chat_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(question="What is this?", scope_type="single_book")
        )

    assert exc_info.value.status_code == 422
    assert "library_item_id is required" in exc_info.value.detail


def test_agent_chat_rejects_empty_multi_book_ids(agent_chat_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(
                question="What is this?",
                scope_type="multi_book",
                library_item_ids=[],
            )
        )

    assert exc_info.value.status_code == 422
    assert "library_item_ids must not be empty" in exc_info.value.detail


def test_agent_chat_rejects_nonexistent_library_item(agent_chat_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(
                question="What is this?",
                scope_type="single_book",
                library_item_id=str(uuid.uuid4()),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Library item not found"
    assert agent_chat_session.execute(select(LearningEvent)).scalars().all() == []


def test_agent_chat_rejects_unindexed_library_item(agent_chat_session) -> None:
    unindexed = create_library_item(agent_chat_session, title="Draft")

    with pytest.raises(HTTPException) as exc_info:
        agent_chat_endpoint(
            AgentChatRequest(
                question="What is this?",
                scope_type="single_book",
                library_item_id=str(unindexed.item_id),
            )
        )

    assert exc_info.value.status_code == 400
    assert "not been indexed" in exc_info.value.detail
    assert agent_chat_session.execute(select(LearningEvent)).scalars().all() == []
