import uuid
from datetime import datetime
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.graphs.schemas import AgentChatRequest, AgentChatResponse, AgentChatScope
from app.learning_events.constants import EVENT_AGENT_CHAT_QUESTION_ASKED, SOURCE_RAG
from app.learning_events.service import create_learning_event
from app.llm.providers import get_llm_provider
from app.memory.long_term import (
    DEFAULT_CONTEXT_MEMORY_COUNT,
    LongTermMemoryResult,
    search_memories,
)
from app.memory.short_term import (
    DEFAULT_RECENT_TURNS_LIMIT,
    ConversationTurnResult,
    create_session_id,
    get_recent_turns,
    save_turn,
)
from app.rag.citations import ChunkCitationResult, build_chunk_citations
from app.rag.qa import build_deterministic_answer, build_rag_prompt
from app.rag.retrieval import (
    LibraryItemRagContext,
    RetrievedChunkResult,
    resolve_library_item_rag_context,
    resolve_library_items_rag_context,
    retrieve_relevant_chunks,
    retrieve_relevant_chunks_for_library_item,
    retrieve_relevant_chunks_for_library_items,
)
from app.rag.schemas import MemoryMetadata, RagCitation, RetrievedChunk, SelectedLibraryItemRead


class ChatRAGGraphError(ValueError):
    """Raised when the Chat RAG graph cannot complete."""


class ChatRAGValidationError(ChatRAGGraphError):
    """Raised when the graph input is invalid."""


class ChatRAGState(TypedDict, total=False):
    question: str
    session_id: str | None
    scope_type: AgentChatScope
    library_item_id: str | None
    library_item_ids: list[str]
    include_long_term_memory: bool
    top_k: int
    selected_library_items: list[dict[str, Any]]
    short_term_context: list[dict[str, Any]]
    long_term_context: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    prompt: str
    answer: str
    memory_metadata: dict[str, Any]
    learning_event_created: bool
    response: dict[str, Any]
    errors: list[str]


def build_chat_rag_graph(session: Session):
    """Build the minimal Chat RAG LangGraph boundary."""
    graph = StateGraph(ChatRAGState)

    graph.add_node("validate_input", validate_input)
    graph.add_node("resolve_scope", lambda state: resolve_scope(state, session))
    graph.add_node("load_memory", lambda state: load_memory(state, session))
    graph.add_node("retrieve_chunks", lambda state: retrieve_chunks(state, session))
    graph.add_node("build_citations", build_citations)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("save_memory", lambda state: save_memory(state, session))
    graph.add_node("record_learning_event", lambda state: record_learning_event(state, session))
    graph.add_node("format_response", format_response)

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "resolve_scope")
    graph.add_edge("resolve_scope", "load_memory")
    graph.add_edge("load_memory", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "build_citations")
    graph.add_edge("build_citations", "build_prompt")
    graph.add_edge("build_prompt", "generate_answer")
    graph.add_edge("generate_answer", "save_memory")
    graph.add_edge("save_memory", "record_learning_event")
    graph.add_edge("record_learning_event", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()


def run_chat_rag_graph(request: AgentChatRequest, session: Session) -> AgentChatResponse:
    """Run the Chat RAG graph for one request using an external transaction boundary."""
    graph = build_chat_rag_graph(session)
    initial_state: ChatRAGState = {
        "question": request.question,
        "session_id": request.session_id or create_session_id(),
        "scope_type": request.scope_type,
        "library_item_id": request.library_item_id,
        "library_item_ids": request.library_item_ids,
        "include_long_term_memory": request.include_long_term_memory,
        "top_k": request.top_k,
        "selected_library_items": [],
        "short_term_context": [],
        "long_term_context": [],
        "retrieved_chunks": [],
        "citations": [],
        "errors": [],
        "learning_event_created": False,
    }
    final_state = graph.invoke(initial_state)
    response = final_state.get("response")
    if response is None:
        raise ChatRAGGraphError("Chat RAG graph did not produce a response")
    return AgentChatResponse.model_validate(response)


def validate_input(state: ChatRAGState) -> ChatRAGState:
    question = state.get("question", "")
    if not question or not question.strip():
        raise ChatRAGValidationError("question must not be empty")

    scope_type = state.get("scope_type")
    if scope_type not in {"global", "single_book", "multi_book"}:
        raise ChatRAGValidationError("scope_type must be global, single_book, or multi_book")

    top_k = state.get("top_k", 5)
    if not isinstance(top_k, int) or not (1 <= top_k <= 20):
        raise ChatRAGValidationError("top_k must be between 1 and 20")

    if scope_type == "single_book":
        library_item_id = (state.get("library_item_id") or "").strip()
        if not library_item_id:
            raise ChatRAGValidationError("library_item_id is required for single_book scope")
        _parse_uuid(library_item_id, "library_item_id")
        return {"library_item_id": library_item_id}

    if scope_type == "multi_book":
        library_item_ids = _normalize_library_item_ids(state.get("library_item_ids", []))
        if not library_item_ids:
            raise ChatRAGValidationError("library_item_ids must not be empty for multi_book scope")
        for item_id in library_item_ids:
            _parse_uuid(item_id, "library_item_ids")
        return {"library_item_ids": library_item_ids}

    return {"library_item_id": None, "library_item_ids": []}


def resolve_scope(state: ChatRAGState, session: Session) -> ChatRAGState:
    """Resolve request scope and validate selected Library items."""
    scope_type = state["scope_type"]
    if scope_type == "single_book":
        selected_item = resolve_library_item_rag_context(
            session, uuid.UUID(state["library_item_id"])
        )
        return {
            "library_item_ids": [state["library_item_id"]],
            "selected_library_items": [_library_item_context_to_state(selected_item)],
        }
    if scope_type == "multi_book":
        library_item_ids = _normalize_library_item_ids(state["library_item_ids"])
        selected_items = resolve_library_items_rag_context(
            session, [uuid.UUID(item_id) for item_id in library_item_ids]
        )
        return {
            "library_item_ids": library_item_ids,
            "selected_library_items": [
                _library_item_context_to_state(item) for item in selected_items
            ],
        }
    return {"selected_library_items": [], "library_item_id": None, "library_item_ids": []}


def load_memory(state: ChatRAGState, session: Session) -> ChatRAGState:
    session_id = state["session_id"]
    recent_turns = get_recent_turns(session, session_id, limit=DEFAULT_RECENT_TURNS_LIMIT)
    long_term_memories = (
        search_memories(
            session,
            keyword=state["question"],
            limit=DEFAULT_CONTEXT_MEMORY_COUNT,
        )
        if state.get("include_long_term_memory", False)
        else []
    )
    return {
        "short_term_context": [_conversation_turn_to_state(turn) for turn in recent_turns],
        "long_term_context": [_long_term_memory_to_state(memory) for memory in long_term_memories],
    }


def retrieve_chunks(state: ChatRAGState, session: Session) -> ChatRAGState:
    scope_type = state["scope_type"]
    question = state["question"]
    top_k = state["top_k"]

    if scope_type == "single_book":
        selected_item, retrieved = retrieve_relevant_chunks_for_library_item(
            session,
            library_item_id=uuid.UUID(state["library_item_id"]),
            question=question,
            top_k=top_k,
        )
        selected_items = [selected_item]
    elif scope_type == "multi_book":
        selected_items, retrieved = retrieve_relevant_chunks_for_library_items(
            session,
            library_item_ids=[uuid.UUID(item_id) for item_id in state["library_item_ids"]],
            question=question,
            top_k=top_k,
        )
    else:
        selected_items = []
        retrieved = retrieve_relevant_chunks(session, question, top_k=top_k)

    return {
        "selected_library_items": [
            _library_item_context_to_state(item) for item in selected_items
        ],
        "retrieved_chunks": [_retrieved_chunk_to_state(chunk) for chunk in retrieved],
    }


def build_citations(state: ChatRAGState) -> ChatRAGState:
    retrieved = [_state_to_retrieved_chunk(chunk) for chunk in state.get("retrieved_chunks", [])]
    citation_results = build_chunk_citations(retrieved)
    return {"citations": [_citation_to_state(citation) for citation in citation_results]}


def build_prompt(state: ChatRAGState) -> ChatRAGState:
    retrieved = [_state_to_retrieved_chunk(chunk) for chunk in state.get("retrieved_chunks", [])]
    recent_turns = [_state_to_conversation_turn(turn) for turn in state["short_term_context"]]
    long_term_memories = [
        _state_to_long_term_memory(memory) for memory in state["long_term_context"]
    ]
    deterministic_answer = build_deterministic_answer(
        state["question"],
        retrieved,
        recent_turns=recent_turns,
        long_term_memories=long_term_memories,
    )
    prompt = build_rag_prompt(
        state["question"],
        retrieved,
        recent_turns=recent_turns,
        long_term_memories=long_term_memories,
        library_item_context=_build_selected_items_context(
            state["scope_type"], state.get("selected_library_items", [])
        ),
        deterministic_answer=deterministic_answer,
    )
    return {"prompt": prompt}


def generate_answer(state: ChatRAGState) -> ChatRAGState:
    provider = get_llm_provider()
    return {"answer": provider.generate(state["prompt"])}


def save_memory(state: ChatRAGState, session: Session) -> ChatRAGState:
    metadata: dict[str, Any] = {
        "query_type": "agent_chat",
        "scope_type": state["scope_type"],
        "retrieved_chunk_ids": [
            chunk["chunk_id"] for chunk in state.get("retrieved_chunks", [])
        ],
        "citation_count": len(state.get("citations", [])),
    }
    if state["scope_type"] == "single_book":
        metadata["library_item_id"] = state["library_item_id"]
    elif state["scope_type"] == "multi_book":
        metadata["library_item_ids"] = state["library_item_ids"]

    save_turn(session, state["session_id"], state["question"], state["answer"], metadata=metadata)
    return {
        "memory_metadata": {
            "used_recent_turns": len(state.get("short_term_context", [])),
            "saved_current_turn": True,
            "used_long_term_memories": len(state.get("long_term_context", [])),
        }
    }


def record_learning_event(state: ChatRAGState, session: Session) -> ChatRAGState:
    selected_items = state.get("selected_library_items", [])
    library_item_id = (
        uuid.UUID(state["library_item_id"]) if state["scope_type"] == "single_book" else None
    )
    create_learning_event(
        session,
        event_type=EVENT_AGENT_CHAT_QUESTION_ASKED,
        title="Agent chat question asked",
        source_type=SOURCE_RAG,
        library_item_id=library_item_id,
        session_id=state["session_id"],
        metadata_json={
            "scope_type": state["scope_type"],
            "library_item_id": state.get("library_item_id"),
            "library_item_ids": state.get("library_item_ids", []),
            "library_titles": [item["title"] for item in selected_items],
            "question": state["question"],
            "total_retrieved": len(state.get("retrieved_chunks", [])),
            "citation_count": len(state.get("citations", [])),
        },
    )
    return {"learning_event_created": True}


def format_response(state: ChatRAGState) -> ChatRAGState:
    citations = [RagCitation.model_validate(citation) for citation in state["citations"]]
    retrieved_chunks = [
        _retrieved_chunk_response(chunk, citation).model_dump()
        for chunk, citation in zip(state.get("retrieved_chunks", []), citations)
    ]
    selected_items = [
        SelectedLibraryItemRead.model_validate(item).model_dump()
        for item in state.get("selected_library_items", [])
    ]
    memory = MemoryMetadata.model_validate(state["memory_metadata"]).model_dump()
    return {
        "response": {
            "answer": state["answer"],
            "scope_type": state["scope_type"],
            "selected_library_items": selected_items,
            "retrieved_chunks": retrieved_chunks,
            "citations": [citation.model_dump() for citation in citations],
            "total_retrieved": len(retrieved_chunks),
            "session_id": state["session_id"],
            "memory": memory,
        }
    }


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ChatRAGValidationError(f"{field_name} must contain valid UUIDs") from exc


def _normalize_library_item_ids(item_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item_id in item_ids:
        stripped = item_id.strip()
        if not stripped:
            raise ChatRAGValidationError("library_item_ids must not contain empty values")
        if stripped not in seen:
            normalized.append(stripped)
            seen.add(stripped)
    return normalized


def _library_item_context_to_state(item: LibraryItemRagContext) -> dict[str, Any]:
    return {
        "id": str(item.item_id),
        "title": item.title,
        "author": item.author,
        "file_type": item.file_type,
        "status": item.status,
    }


def _conversation_turn_to_state(turn: ConversationTurnResult) -> dict[str, Any]:
    return {
        "turn_id": str(turn.turn_id),
        "session_id": turn.session_id,
        "question": turn.question,
        "answer": turn.answer,
        "created_at": turn.created_at.isoformat(),
    }


def _state_to_conversation_turn(data: dict[str, Any]) -> ConversationTurnResult:
    return ConversationTurnResult(
        turn_id=uuid.UUID(data["turn_id"]),
        session_id=data["session_id"],
        question=data["question"],
        answer=data["answer"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _long_term_memory_to_state(memory: LongTermMemoryResult) -> dict[str, Any]:
    return {
        "memory_id": str(memory.memory_id),
        "memory_type": memory.memory_type,
        "content": memory.content,
        "importance": memory.importance,
        "source": memory.source,
        "tags": memory.tags,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
    }


def _state_to_long_term_memory(data: dict[str, Any]) -> LongTermMemoryResult:
    return LongTermMemoryResult(
        memory_id=uuid.UUID(data["memory_id"]),
        memory_type=data["memory_type"],
        content=data["content"],
        importance=data["importance"],
        source=data.get("source"),
        tags=data.get("tags"),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )


def _retrieved_chunk_to_state(chunk: RetrievedChunkResult) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "document_source_path": chunk.document_source_path,
        "library_item_id": str(chunk.library_item_id) if chunk.library_item_id else None,
        "library_title": chunk.library_title,
        "library_author": chunk.library_author,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "score": chunk.score,
    }


def _state_to_retrieved_chunk(data: dict[str, Any]) -> RetrievedChunkResult:
    return RetrievedChunkResult(
        chunk_id=uuid.UUID(data["chunk_id"]),
        document_id=uuid.UUID(data["document_id"]),
        document_title=data.get("document_title"),
        document_source_path=data.get("document_source_path"),
        library_item_id=uuid.UUID(data["library_item_id"])
        if data.get("library_item_id")
        else None,
        library_title=data.get("library_title"),
        library_author=data.get("library_author"),
        chunk_index=data["chunk_index"],
        content=data["content"],
        char_start=data["char_start"],
        char_end=data["char_end"],
        score=data["score"],
    )


def _citation_to_state(citation: ChunkCitationResult) -> dict[str, Any]:
    return {
        "citation_id": citation.citation_id,
        "chunk_id": citation.chunk_id,
        "document_id": citation.document_id,
        "library_item_id": citation.library_item_id,
        "library_title": citation.library_title,
        "library_author": citation.library_author,
        "document_title": citation.document_title,
        "document_source_path": citation.document_source_path,
        "chunk_index": citation.chunk_index,
        "score": citation.score,
        "excerpt": citation.excerpt,
        "content": citation.content,
    }


def _retrieved_chunk_response(
    chunk: dict[str, Any], citation: RagCitation
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk["chunk_id"],
        document_id=chunk["document_id"],
        document_title=chunk.get("document_title"),
        document_source_path=chunk.get("document_source_path"),
        chunk_index=chunk["chunk_index"],
        content=chunk["content"],
        char_start=chunk["char_start"],
        char_end=chunk["char_end"],
        score=chunk["score"],
        citation=citation,
    )


def _build_selected_items_context(
    scope_type: Literal["global", "single_book", "multi_book"],
    selected_items: list[dict[str, Any]],
) -> str | None:
    if scope_type == "global" or not selected_items:
        return None

    lines = ["Selected books:"]
    for index, item in enumerate(selected_items, start=1):
        parts = [f"{index}. {item['title']}", f"status: {item['status']}"]
        if item.get("author"):
            parts.append(f"author: {item['author']}")
        if item.get("file_type"):
            parts.append(f"file type: {item['file_type']}")
        lines.append("; ".join(parts))
    return "\n".join(lines)
