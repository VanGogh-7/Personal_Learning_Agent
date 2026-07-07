import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.api.agent_routes as agent_routes_module
from app.api.agent_routes import agent_chat_endpoint
from app.embeddings.base import EMBEDDING_DIMENSION
from app.graphs.schemas import AgentChatRequest
from app.learning_events.constants import EVENT_AGENT_CHAT_QUESTION_ASKED
from app.library.indexing import index_library_item
from app.library.service import create_library_item
from app.models.conversation_turn import ConversationTurn
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.learning_event import LearningEvent
from app.models.library_item import LibraryItem
from app.models.note import Note
from tests.pdf_fixtures import make_pdf_bytes


def test_pdf_library_item_indexes_and_answers_through_agent_chat(
    monkeypatch, tmp_path
) -> None:
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
        pdf_path = tmp_path / "calculus.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "Euler equations describe stationary action in calculus.",
                    "Boundary terms vanish for fixed endpoint variations.",
                ]
            )
        )
        item = create_library_item(
            session,
            title="Calculus PDF",
            file_path=str(pdf_path),
            file_type="pdf",
        )

        index_result = index_library_item(session, item.item_id)

        assert index_result is not None
        assert index_result.status == "indexed"
        assert index_result.chunks_created == 2
        assert index_result.embeddings_created == 2

        document = session.get(Document, index_result.document_id)
        assert document is not None
        assert document.library_item_id == item.item_id
        assert document.file_path == str(pdf_path)
        assert document.file_type == "pdf"
        assert document.content_hash

        chunks = session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars().all()
        assert len(chunks) == 2
        assert [chunk.page_start for chunk in chunks] == [1, 2]
        assert [chunk.page_end for chunk in chunks] == [1, 2]
        assert all(chunk.embedding is not None for chunk in chunks)
        assert all(len(chunk.embedding) == EMBEDDING_DIMENSION for chunk in chunks)

        response = agent_chat_endpoint(
            AgentChatRequest(
                question="What do Euler equations describe?",
                scope_type="single_book",
                library_item_id=str(item.item_id),
                top_k=2,
                session_id="pdf-rag-session",
            )
        )

        assert response.scope_type == "single_book"
        assert response.selected_library_items[0].id == str(item.item_id)
        assert response.selected_library_items[0].file_type == "pdf"
        assert response.total_retrieved == 2
        assert response.answer
        assert response.citations
        assert {citation.page_number for citation in response.citations} == {1, 2}
        assert {citation.document_id for citation in response.citations} == {
            str(document.id)
        }
        assert {citation.library_item_id for citation in response.citations} == {
            str(item.item_id)
        }
        assert all(
            citation.document_source_path == str(pdf_path)
            for citation in response.citations
        )
        assert response.retrieved_chunks[0].citation == response.citations[0]
        assert all(chunk.page_start in {1, 2} for chunk in response.retrieved_chunks)

        turn = session.execute(select(ConversationTurn)).scalar_one()
        assert turn.session_id == "pdf-rag-session"
        assert turn.metadata_json["scope_type"] == "single_book"
        assert turn.metadata_json["library_item_id"] == str(item.item_id)

        event = session.execute(select(LearningEvent)).scalar_one()
        assert event.event_type == EVENT_AGENT_CHAT_QUESTION_ASKED
        assert event.library_item_id == item.item_id
        assert event.metadata_json["total_retrieved"] == 2
        assert event.metadata_json["citation_count"] == 2
    finally:
        close_session()
        engine.dispose()
