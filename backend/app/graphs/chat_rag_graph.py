import uuid
import logging
from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents.local_library import (
    LocalLibraryAgentResult,
    run_local_library_agent as run_local_library_agent_service,
)
from app.agents.router import AgentRoute, route_question
from app.agents.synthesis import prepare_agent_synthesis, synthesize_agent_answer
from app.agents.web_research import (
    WebResearchResult,
    WebSourceResult,
    run_web_research_agent as run_web_research_agent_service,
)
from app.graphs.schemas import AgentChatRequest, AgentChatResponse, AgentChatScope
from app.learning_events.constants import EVENT_AGENT_CHAT_QUESTION_ASKED, SOURCE_RAG
from app.learning_events.service import create_learning_event
from app.llm.providers import LLMProviderError, TokenUsage, get_llm_provider
from app.memory.long_term import (
    LongTermMemoryResult,
)
from app.memory.checkpointer import checkpointer_manager
from app.memory.context_builder import (
    build_memory_context,
    render_untrusted_memory_context,
)
from app.memory.conversations import (
    ConversationIdentity,
    ensure_conversation,
    resolve_conversation,
)
from app.core.config import get_settings
from app.memory.service import (
    extract_and_consolidate_turn,
    maintain_conversation_summary,
    run_post_response_memory_processing,
)
from app.memory.short_term import (
    ConversationTurnResult,
    save_turn,
)
from app.rag.citations import ChunkCitationResult
from app.rag.retrieval import (
    LibraryItemRagContext,
    RetrievedChunkResult,
    resolve_library_item_rag_context,
    resolve_library_items_rag_context,
    retrieve_relevant_chunks,
    retrieve_relevant_chunks_for_library_item,
    retrieve_relevant_chunks_for_library_items,
)
from app.rag.schemas import (
    MemoryMetadata,
    RagCitation,
    RetrievedChunk,
    SelectedLibraryItemRead,
)
from app.observability.checkpointer import TimedCheckpointer
from app.observability.latency import current_latency_trace, measure_latency_sync

logger = logging.getLogger(__name__)


class ChatRAGGraphError(ValueError):
    """Raised when the Chat RAG graph cannot complete."""


class ChatRAGValidationError(ChatRAGGraphError):
    """Raised when the graph input is invalid."""


class AgentGraphState(TypedDict, total=False):
    # Stable graph contract for the dual-agent MVP. Values are kept JSON-like
    # because LangGraph passes state between independent node functions.
    user_message: str
    selected_library_item_ids: list[str]
    route_decision: AgentRoute
    local_results: dict[str, Any] | None
    web_results: dict[str, Any] | None
    final_answer: str
    local_citations: list[dict[str, Any]]
    web_sources: list[dict[str, Any]]
    warnings: list[str]
    errors: list[str]
    question: str
    session_id: str | None
    conversation_id: str
    thread_id: str
    memory_namespace: str
    scope_type: AgentChatScope
    library_item_id: str | None
    library_item_ids: list[str]
    include_long_term_memory: bool
    top_k: int
    route: AgentRoute
    selected_library_items: list[dict[str, Any]]
    short_term_context: list[dict[str, Any]]
    long_term_context: list[dict[str, Any]]
    conversation_summary: str
    memory_prompt_context: str
    memory_updates: list[dict[str, Any]]
    summary_updated: bool
    retrieved_chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    local_summary: str | None
    web_summary: str | None
    prompt: str
    answer: str
    memory_metadata: dict[str, Any]
    learning_event_created: bool
    persisted_turn_id: str
    persisted_learning_event_id: str
    conversation_created: bool
    response: dict[str, Any]


ChatRAGState = AgentGraphState


def build_chat_rag_graph(
    session: Session,
    checkpointer=None,
    background_tasks=None,
    background_session_factory=None,
):
    """Build the explicit dual-agent LangGraph boundary."""
    graph = StateGraph(AgentGraphState)

    graph.add_node("validate_input", validate_input)
    graph.add_node("resolve_scope", lambda state: resolve_scope(state, session))
    graph.add_node("load_memory", lambda state: load_memory(state, session))
    graph.add_node("router_node", router_node)
    graph.add_node(
        "local_library_agent_node",
        lambda state: run_local_node_with_independent_session(state, session),
    )
    graph.add_node("web_research_agent_node", web_research_agent_node)
    graph.add_node("synthesis_node", synthesis_node)
    graph.add_node(
        "save_memory",
        lambda state: save_memory(
            state,
            session,
            background_tasks=background_tasks,
            background_session_factory=background_session_factory,
        ),
    )
    graph.add_node(
        "record_learning_event", lambda state: record_learning_event(state, session)
    )
    graph.add_node("format_response", format_response)

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "resolve_scope")
    graph.add_edge("resolve_scope", "load_memory")
    graph.add_edge("load_memory", "router_node")
    graph.add_edge("router_node", "local_library_agent_node")
    graph.add_edge("router_node", "web_research_agent_node")
    graph.add_edge("local_library_agent_node", "synthesis_node")
    graph.add_edge("web_research_agent_node", "synthesis_node")
    graph.add_edge("synthesis_node", "save_memory")
    graph.add_edge("save_memory", "record_learning_event")
    graph.add_edge("record_learning_event", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile(checkpointer=checkpointer)


def build_streaming_chat_rag_graph(
    *,
    session_factory: Callable[[], Session],
    deferred_tasks: Any,
    persistence_receipt: dict[str, Any],
    checkpointer: Any,
):
    """Build the async SSE graph while reusing the stable Agent node services."""
    graph = StateGraph(AgentGraphState)
    graph.add_node("validate_input", validate_input)
    graph.add_node(
        "resolve_scope",
        lambda state: streaming_resolve_scope_node(state, session_factory),
    )
    graph.add_node(
        "load_memory",
        lambda state: streaming_load_memory_node(state, session_factory),
    )
    graph.add_node("router_node", streaming_router_node)
    graph.add_node(
        "local_library_agent_node",
        lambda state: streaming_local_node(state, session_factory),
    )
    graph.add_node("web_research_agent_node", streaming_web_node)
    graph.add_node("synthesis_node", streaming_synthesis_node)
    graph.add_node(
        "persist_final",
        lambda state: streaming_persist_node(
            state,
            session_factory=session_factory,
            deferred_tasks=deferred_tasks,
            persistence_receipt=persistence_receipt,
        ),
    )
    graph.add_node("format_response", format_response)

    graph.set_entry_point("validate_input")
    graph.add_edge("validate_input", "resolve_scope")
    graph.add_edge("resolve_scope", "load_memory")
    graph.add_edge("load_memory", "router_node")
    graph.add_edge("router_node", "local_library_agent_node")
    graph.add_edge("router_node", "web_research_agent_node")
    graph.add_edge("local_library_agent_node", "synthesis_node")
    graph.add_edge("web_research_agent_node", "synthesis_node")
    graph.add_edge("synthesis_node", "persist_final")
    graph.add_edge("persist_final", "format_response")
    graph.add_edge("format_response", END)
    return graph.compile(checkpointer=checkpointer)


def streaming_resolve_scope_node(
    state: ChatRAGState, session_factory: Callable[[], Session]
) -> ChatRAGState:
    _write_activity("loading_context", "正在读取会话上下文")
    session = session_factory()
    try:
        return resolve_scope(state, session)
    finally:
        session.rollback()
        session.close()


def streaming_load_memory_node(
    state: ChatRAGState, session_factory: Callable[[], Session]
) -> ChatRAGState:
    _write_activity("retrieving_memory", "正在检索相关记忆")
    session = session_factory()
    try:
        return load_memory(state, session)
    finally:
        session.rollback()
        session.close()


def streaming_router_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("routing", "正在分析问题")
    result = router_node(state)
    _write_custom({"kind": "route_selected", "route": result["route"]})
    return result


def streaming_local_node(
    state: ChatRAGState, session_factory: Callable[[], Session]
) -> ChatRAGState:
    session = session_factory()
    try:
        if state["route"] == "web_only":
            return local_library_agent_node(state, session)
        _write_activity("retrieving_local", "正在检索已选书籍")
        result = local_library_agent_node(state, session)
    finally:
        session.rollback()
        session.close()
    _write_custom(
        {
            "kind": "retrieval_completed",
            "source": "local",
            "result_count": len(result.get("retrieved_chunks", [])),
        }
    )
    return result


def streaming_web_node(state: ChatRAGState) -> ChatRAGState:
    if state["route"] == "local_only":
        return web_research_agent_node(state)
    _write_activity("searching_web", "正在搜索网络资料")
    result = web_research_agent_node(state)
    _write_custom(
        {
            "kind": "retrieval_completed",
            "source": "web",
            "result_count": len(result.get("web_sources", [])),
        }
    )
    return result


async def streaming_synthesis_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("processing_sources", "正在整合本地与网络证据")
    local_result = _state_to_local_library_agent_result(state)
    web_result = _state_to_web_research_result(state)
    prepared = prepare_agent_synthesis(
        question=state["question"],
        route=state["route"],
        local_result=local_result,
        web_result=web_result,
        memory_context=state.get("memory_prompt_context", ""),
    )
    _write_activity("synthesizing", "正在生成回答")
    provider = get_llm_provider()
    started_at = perf_counter()
    first_token_at: float | None = None
    last_token_at: float | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    chunks: list[str] = []
    async for chunk in provider.stream_chat_completion(prepared.prompt):
        if chunk.usage is not None:
            usage = chunk.usage
        if chunk.finish_reason is not None:
            finish_reason = chunk.finish_reason
        if not chunk.delta:
            continue
        now = perf_counter()
        if first_token_at is None:
            first_token_at = now
            _write_activity("streaming", "正在生成回答")
        last_token_at = now
        chunks.append(chunk.delta)
        _write_custom({"kind": "synthesis_token", "delta": chunk.delta})

    answer = "".join(chunks)
    if not answer.strip() or first_token_at is None or last_token_at is None:
        raise LLMProviderError("Final synthesis returned no visible content.")
    if finish_reason != "stop":
        raise LLMProviderError(
            f"Final synthesis did not complete normally ({finish_reason or 'missing'})."
        )
    trace = current_latency_trace()
    if trace is not None:
        trace.record("synthesis_ttft", (first_token_at - started_at) * 1000)
        trace.record("synthesis_generation", (last_token_at - first_token_at) * 1000)
        trace.record("synthesis_total", (last_token_at - started_at) * 1000)
        trace.set_counter(
            "prompt_input_tokens", usage.prompt_tokens if usage is not None else None
        )
        trace.set_counter(
            "completion_tokens",
            usage.completion_tokens if usage is not None else None,
        )
        trace.set_counter("output_character_count", len(answer))
        trace.set_counter("streaming_enabled", True)
    return {
        "answer": answer,
        "final_answer": answer,
        "local_summary": prepared.local_summary,
        "web_summary": prepared.web_summary,
        "warnings": _merge_unique_strings(state.get("warnings", []), prepared.warnings),
        "errors": _merge_unique_strings(state.get("errors", []), prepared.errors),
    }


def streaming_persist_node(
    state: ChatRAGState,
    *,
    session_factory: Callable[[], Session],
    deferred_tasks: Any,
    persistence_receipt: dict[str, Any],
) -> ChatRAGState:
    _write_activity("persisting", "正在保存完整回答")
    session = session_factory()
    try:
        with measure_latency_sync("final_persist"):
            created = ensure_conversation(
                session,
                conversation_id=uuid.UUID(state["conversation_id"]),
                thread_id=state["thread_id"],
                session_id=state["session_id"],
                namespace=state["memory_namespace"],
            )
            memory_state = save_memory(
                state,
                session,
                background_tasks=deferred_tasks,
                background_session_factory=session_factory,
            )
            event_state = record_learning_event({**state, **memory_state}, session)
            session.commit()
        result = {
            **memory_state,
            **event_state,
            "conversation_created": created,
        }
        persistence_receipt.update(result)
        persistence_receipt["conversation_id"] = state["conversation_id"]
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _write_activity(stage: str, message: str) -> None:
    if get_settings().agent_activity_events_enabled:
        _write_custom({"kind": "status", "stage": stage, "message": message})


def _write_custom(payload: dict[str, Any]) -> None:
    get_stream_writer()(payload)


def run_local_node_with_independent_session(
    state: ChatRAGState, request_session: Session
) -> ChatRAGState:
    """Use a read-only session so Local and Web can execute concurrently."""
    if request_session.get_bind().dialect.name == "sqlite":
        # SQLite test fixtures may use one StaticPool connection. A second
        # session rollback would also roll back the request transaction.
        return local_library_agent_node(state, request_session)
    local_session = Session(bind=request_session.get_bind(), expire_on_commit=False)
    try:
        return local_library_agent_node(state, local_session)
    finally:
        local_session.rollback()
        local_session.close()


def run_chat_rag_graph(
    request: AgentChatRequest,
    session: Session,
    *,
    background_tasks=None,
    background_session_factory=None,
) -> AgentChatResponse:
    """Run the Chat RAG graph for one request using an external transaction boundary."""
    try:
        requested_conversation_id = (
            uuid.UUID(request.conversation_id) if request.conversation_id else None
        )
        with measure_latency_sync("conversation_load"):
            conversation = resolve_conversation(
                session,
                conversation_id=requested_conversation_id,
                legacy_session_id=request.session_id,
            )
    except ValueError as exc:
        raise ChatRAGValidationError(str(exc)) from exc
    trace = current_latency_trace()
    if trace is not None:
        trace.conversation_id = str(conversation.conversation_id)
    graph = build_chat_rag_graph(
        session,
        TimedCheckpointer(checkpointer_manager.get()),
        background_tasks=background_tasks,
        background_session_factory=background_session_factory,
    )
    initial_state = build_initial_agent_state(request, conversation)
    final_state = graph.invoke(
        initial_state,
        {"configurable": {"thread_id": conversation.thread_id}},
    )
    response = final_state.get("response")
    if response is None:
        raise ChatRAGGraphError("Chat RAG graph did not produce a response")
    return AgentChatResponse.model_validate(response)


def build_initial_agent_state(
    request: AgentChatRequest, conversation: ConversationIdentity
) -> AgentGraphState:
    selected_library_item_ids = request.library_item_ids or (
        [request.library_item_id] if request.library_item_id else []
    )
    return {
        "user_message": request.question or request.message or "",
        "selected_library_item_ids": selected_library_item_ids,
        "question": request.question or request.message or "",
        "session_id": conversation.session_id,
        "conversation_id": str(conversation.conversation_id),
        "thread_id": conversation.thread_id,
        "memory_namespace": conversation.namespace,
        "scope_type": request.scope_type,
        "library_item_id": request.library_item_id,
        "library_item_ids": request.library_item_ids,
        "include_long_term_memory": request.include_long_term_memory,
        "top_k": request.top_k,
        "selected_library_items": [],
        "short_term_context": [],
        "long_term_context": [],
        "conversation_summary": "",
        "memory_prompt_context": "",
        "memory_updates": [],
        "summary_updated": False,
        "retrieved_chunks": [],
        "citations": [],
        "web_sources": [],
        "local_citations": [],
        "local_summary": None,
        "web_summary": None,
        "warnings": [],
        "errors": [],
        "learning_event_created": False,
    }


def validate_input(state: ChatRAGState) -> ChatRAGState:
    with measure_latency_sync("request_validation"):
        return _validate_input(state)


def _validate_input(state: ChatRAGState) -> ChatRAGState:
    question = state.get("question", "")
    if not question or not question.strip():
        raise ChatRAGValidationError("question must not be empty")

    scope_type = state.get("scope_type")
    if scope_type not in {"global", "single_book", "multi_book"}:
        raise ChatRAGValidationError(
            "scope_type must be global, single_book, or multi_book"
        )

    top_k = state.get("top_k", 5)
    if not isinstance(top_k, int) or not (1 <= top_k <= 20):
        raise ChatRAGValidationError("top_k must be between 1 and 20")

    if scope_type == "single_book":
        library_item_id = (state.get("library_item_id") or "").strip()
        if not library_item_id:
            raise ChatRAGValidationError(
                "library_item_id is required for single_book scope"
            )
        _parse_uuid(library_item_id, "library_item_id")
        return {"library_item_id": library_item_id}

    if scope_type == "multi_book":
        library_item_ids = _normalize_library_item_ids(
            state.get("library_item_ids", [])
        )
        if not library_item_ids:
            raise ChatRAGValidationError(
                "library_item_ids must not be empty for multi_book scope"
            )
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
    return {
        "selected_library_items": [],
        "library_item_id": None,
        "library_item_ids": [],
    }


def load_memory(state: ChatRAGState, session: Session) -> ChatRAGState:
    with measure_latency_sync("memory_load_total"):
        context = build_memory_context(
            session,
            conversation_id=uuid.UUID(state["conversation_id"]),
            namespace=state["memory_namespace"],
            query=state["question"],
        )
    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter(
            "recent_turn_characters",
            sum(len(turn.question) + len(turn.answer) for turn in context.recent_turns),
        )
        trace.set_counter(
            "conversation_summary_characters", len(context.rolling_summary)
        )
        trace.set_counter(
            "retrieved_memory_characters",
            sum(len(memory.content) for memory in context.long_term_memories),
        )
    return {
        "short_term_context": [
            _conversation_turn_to_state(turn) for turn in context.recent_turns
        ],
        "long_term_context": [
            {
                "memory_id": str(memory.id),
                "memory_type": memory.memory_type,
                "memory_subtype": memory.memory_subtype,
                "content": memory.content,
                "importance": max(1, round(memory.importance * 5)),
                "confidence": memory.confidence,
            }
            for memory in context.long_term_memories
        ],
        "conversation_summary": context.rolling_summary,
        "memory_prompt_context": render_untrusted_memory_context(context),
    }


def router_node(state: ChatRAGState) -> ChatRAGState:
    # Routing is intentionally deterministic so MVP demos and tests are stable.
    with measure_latency_sync("router_total"):
        route = route_question(state["question"])
    trace = current_latency_trace()
    if trace is not None:
        trace.route = route
        trace.set_counter("route", route)
        trace.set_counter(
            "selected_library_item_count",
            len(state.get("selected_library_items", [])),
        )
    return {"route": route, "route_decision": route}


def local_library_agent_node(state: ChatRAGState, session: Session) -> ChatRAGState:
    # The local agent owns pgvector retrieval and [S#] citation creation.
    if state["route"] == "web_only":
        return {
            "retrieved_chunks": [],
            "citations": [],
            "local_citations": [],
            "local_summary": None,
            "local_results": {
                "summary": None,
                "evidence_quality": "none",
                "total_retrieved": 0,
                "selected_library_items": state.get("selected_library_items", []),
                "retrieved_chunks": [],
                "citations": [],
                "skipped": True,
            },
        }

    recent_turns = [
        _state_to_conversation_turn(turn) for turn in state["short_term_context"]
    ]
    long_term_memories = [
        _state_to_long_term_memory(memory) for memory in state["long_term_context"]
    ]
    with measure_latency_sync("local_agent_total"):
        result = run_local_library_agent_service(
            session,
            question=state["question"],
            scope_type=state["scope_type"],
            library_item_id=state.get("library_item_id"),
            library_item_ids=state.get("library_item_ids", []),
            top_k=state["top_k"],
            recent_turns=recent_turns,
            long_term_memories=long_term_memories,
            retrieve_global=retrieve_relevant_chunks,
            retrieve_single_book=retrieve_relevant_chunks_for_library_item,
            retrieve_multi_book=retrieve_relevant_chunks_for_library_items,
        )
    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter("retrieved_chunk_count", len(result.retrieved_chunks))
    return _local_library_agent_result_to_state(result)


def web_research_agent_node(state: ChatRAGState) -> ChatRAGState:
    # The web agent is provider-backed and always returns structured [W#] sources.
    if state["route"] == "local_only":
        return {
            "web_summary": None,
            "web_sources": [],
            "web_results": {
                "summary": None,
                "sources": [],
                "status": "skipped",
                "warnings": [],
                "errors": [],
                "skipped": True,
            },
        }

    trace = current_latency_trace()
    if trace is not None:
        trace.increment("web_search_call_count")
        if get_settings().web_research_provider.strip().lower() == "tavily":
            trace.increment("tavily_call_count")
    with measure_latency_sync("web_agent_total"):
        with measure_latency_sync("web_search"):
            result = run_web_research_agent_service(state["question"])
        with measure_latency_sync("web_result_processing"):
            result_state = _web_research_result_to_state(result)
    if trace is not None:
        trace.set_counter("web_result_count", len(result.sources))
    return result_state


def synthesis_node(state: ChatRAGState) -> ChatRAGState:
    # Synthesis combines agent outputs without merging local citations and web sources.
    local_result = _state_to_local_library_agent_result(state)
    web_result = _state_to_web_research_result(state)
    synthesis = synthesize_agent_answer(
        question=state["question"],
        route=state["route"],
        local_result=local_result,
        web_result=web_result,
        llm_provider=get_llm_provider(),
        memory_context=state.get("memory_prompt_context", ""),
    )
    return {
        "answer": synthesis.answer,
        "final_answer": synthesis.answer,
        "local_summary": synthesis.local_summary,
        "web_summary": synthesis.web_summary,
        "warnings": _merge_unique_strings(
            state.get("warnings", []), synthesis.warnings
        ),
        "errors": _merge_unique_strings(state.get("errors", []), synthesis.errors),
    }


def save_memory(
    state: ChatRAGState,
    session: Session,
    *,
    background_tasks=None,
    background_session_factory=None,
) -> ChatRAGState:
    metadata: dict[str, Any] = {
        "query_type": "agent_chat",
        "scope_type": state["scope_type"],
        "retrieved_chunk_ids": [
            chunk["chunk_id"] for chunk in state.get("retrieved_chunks", [])
        ],
        "citation_count": len(state.get("citations", [])),
        "citations": state.get("citations", []),
        "citation_refs": [
            {
                key: citation.get(key)
                for key in (
                    "citation_id",
                    "chunk_id",
                    "document_id",
                    "library_item_id",
                    "page_start",
                    "page_end",
                )
            }
            for citation in state.get("citations", [])
        ],
        "web_source_refs": [
            {key: source.get(key) for key in ("source_id", "title", "url", "provider")}
            for source in state.get("web_sources", [])
        ],
        "web_sources": state.get("web_sources", []),
    }
    if state["scope_type"] == "single_book":
        metadata["library_item_id"] = state["library_item_id"]
    elif state["scope_type"] == "multi_book":
        metadata["library_item_ids"] = state["library_item_ids"]

    with measure_latency_sync("conversation_persist"):
        turn = save_turn(
            session,
            state["session_id"],
            state["question"],
            state["answer"],
            metadata=metadata,
            conversation_id=uuid.UUID(state["conversation_id"]),
        )
    memory_updates: list[dict[str, Any]] = []
    summary_updated = False
    if background_tasks is not None:
        trace = current_latency_trace()
        background_tasks.add_task(
            run_post_response_memory_processing,
            request_id=trace.request_id if trace is not None else str(uuid.uuid4()),
            conversation_id=uuid.UUID(state["conversation_id"]),
            namespace=state["memory_namespace"],
            source_turn_id=turn.turn_id,
            user_message=state["question"],
            route=state["route"],
            session_factory=background_session_factory,
        )
        if trace is not None:
            trace.set_counter("memory_post_processing_deferred", True)
        return {
            "memory_metadata": {
                "used_recent_turns": len(state.get("short_term_context", [])),
                "saved_current_turn": True,
                "used_long_term_memories": len(state.get("long_term_context", [])),
            },
            "memory_updates": memory_updates,
            "summary_updated": summary_updated,
            "persisted_turn_id": str(turn.turn_id),
        }
    try:
        with session.begin_nested():
            with measure_latency_sync("conversation_summary"):
                summary_updated = maintain_conversation_summary(
                    session, conversation_id=uuid.UUID(state["conversation_id"])
                )
    except Exception as exc:
        logger.warning(
            "memory_summary_failed conversation_id=%s thread_id=%s error_type=%s",
            state["conversation_id"],
            state["thread_id"],
            type(exc).__name__,
        )
    try:
        with session.begin_nested():
            results = extract_and_consolidate_turn(
                session,
                conversation_id=uuid.UUID(state["conversation_id"]),
                namespace=state["memory_namespace"],
                source_turn_id=turn.turn_id,
                user_message=state["question"],
            )
            memory_updates = [
                {"stored": result.memory_id is not None, "action": result.action.value}
                for result in results
            ]
    except Exception as exc:
        logger.warning(
            "memory_extraction_failed conversation_id=%s thread_id=%s error_type=%s",
            state["conversation_id"],
            state["thread_id"],
            type(exc).__name__,
        )
    return {
        "memory_metadata": {
            "used_recent_turns": len(state.get("short_term_context", [])),
            "saved_current_turn": True,
            "used_long_term_memories": len(state.get("long_term_context", [])),
        },
        "memory_updates": memory_updates,
        "summary_updated": summary_updated,
        "persisted_turn_id": str(turn.turn_id),
    }


def record_learning_event(state: ChatRAGState, session: Session) -> ChatRAGState:
    selected_items = state.get("selected_library_items", [])
    library_item_id = (
        uuid.UUID(state["library_item_id"])
        if state["scope_type"] == "single_book"
        else None
    )
    result = create_learning_event(
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
    return {
        "learning_event_created": True,
        "persisted_learning_event_id": str(result.event_id),
    }


def format_response(state: ChatRAGState) -> ChatRAGState:
    with measure_latency_sync("response_serialization"):
        return _format_response(state)


def _format_response(state: ChatRAGState) -> ChatRAGState:
    citations = [
        RagCitation.model_validate(citation) for citation in state["citations"]
    ]
    local_citations = [
        RagCitation.model_validate(citation)
        for citation in state.get("local_citations", state["citations"])
    ]
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
            "route": state["route"],
            "selected_library_items": selected_items,
            "retrieved_chunks": retrieved_chunks,
            "citations": [citation.model_dump() for citation in citations],
            "local_citations": [citation.model_dump() for citation in local_citations],
            "web_sources": state.get("web_sources", []),
            "warnings": state.get("warnings", []),
            "errors": state.get("errors", []),
            "local_summary": state.get("local_summary"),
            "web_summary": state.get("web_summary"),
            "total_retrieved": len(retrieved_chunks),
            "session_id": state["session_id"],
            "conversation_id": state["conversation_id"],
            "memory_updates": state.get("memory_updates", []),
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
            raise ChatRAGValidationError(
                "library_item_ids must not contain empty values"
            )
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


def _state_to_library_item_context(data: dict[str, Any]) -> LibraryItemRagContext:
    return LibraryItemRagContext(
        item_id=uuid.UUID(data["id"]),
        title=data["title"],
        author=data.get("author"),
        file_type=data.get("file_type"),
        status=data["status"],
    )


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
    now = datetime.now().astimezone()
    return LongTermMemoryResult(
        memory_id=uuid.UUID(data["memory_id"]),
        memory_type=data["memory_type"],
        content=data["content"],
        importance=data["importance"],
        source=data.get("source", "memory_retrieval"),
        tags=data.get("tags"),
        created_at=datetime.fromisoformat(data["created_at"])
        if data.get("created_at")
        else now,
        updated_at=datetime.fromisoformat(data["updated_at"])
        if data.get("updated_at")
        else now,
    )


def _retrieved_chunk_to_state(chunk: RetrievedChunkResult) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "document_source_path": chunk.document_source_path,
        "library_item_id": str(chunk.library_item_id)
        if chunk.library_item_id
        else None,
        "library_title": chunk.library_title,
        "library_author": chunk.library_author,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section_type": chunk.section_type,
        "chapter_title": chunk.chapter_title,
        "section_title": chunk.section_title,
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
        page_start=data.get("page_start"),
        page_end=data.get("page_end"),
        section_type=data.get("section_type", "unknown"),
        chapter_title=data.get("chapter_title"),
        section_title=data.get("section_title"),
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
        "page_number": citation.page_number,
        "page_start": citation.page_start,
        "page_end": citation.page_end,
        "section_type": citation.section_type,
        "chapter_title": citation.chapter_title,
        "section_title": citation.section_title,
        "score": citation.score,
        "excerpt": citation.excerpt,
        "content": citation.content,
    }


def _state_to_citation_result(data: dict[str, Any]) -> ChunkCitationResult:
    return ChunkCitationResult(
        citation_id=data["citation_id"],
        chunk_id=data["chunk_id"],
        document_id=data["document_id"],
        library_item_id=data.get("library_item_id"),
        library_title=data.get("library_title"),
        library_author=data.get("library_author"),
        document_title=data.get("document_title"),
        document_source_path=data.get("document_source_path"),
        chunk_index=data["chunk_index"],
        page_number=data.get("page_number"),
        page_start=data.get("page_start"),
        page_end=data.get("page_end"),
        section_type=data.get("section_type", "unknown"),
        chapter_title=data.get("chapter_title"),
        section_title=data.get("section_title"),
        score=data["score"],
        excerpt=data["excerpt"],
        content=data["content"],
    )


def _local_library_agent_result_to_state(
    result: LocalLibraryAgentResult,
) -> dict[str, Any]:
    selected_items = [
        _library_item_context_to_state(item) for item in result.selected_library_items
    ]
    retrieved_chunks = [
        _retrieved_chunk_to_state(chunk) for chunk in result.retrieved_chunks
    ]
    citations = [_citation_to_state(citation) for citation in result.citations]
    return {
        "selected_library_items": selected_items,
        "retrieved_chunks": retrieved_chunks,
        "citations": citations,
        "local_citations": citations,
        "local_summary": result.summary,
        "local_results": {
            "summary": result.summary,
            "evidence_quality": result.evidence_quality,
            "total_retrieved": len(result.retrieved_chunks),
            "selected_library_items": selected_items,
            "retrieved_chunks": retrieved_chunks,
            "citations": citations,
            "skipped": False,
        },
    }


def _state_to_local_library_agent_result(
    state: ChatRAGState,
) -> LocalLibraryAgentResult | None:
    if state.get("local_summary") is None and not state.get("retrieved_chunks"):
        return None

    return LocalLibraryAgentResult(
        summary=state.get("local_summary") or "",
        selected_library_items=[
            _state_to_library_item_context(item)
            for item in state.get("selected_library_items", [])
        ],
        retrieved_chunks=[
            _state_to_retrieved_chunk(chunk)
            for chunk in state.get("retrieved_chunks", [])
        ],
        citations=[
            _state_to_citation_result(citation)
            for citation in state.get("citations", [])
        ],
        evidence_quality=(state.get("local_results", {}) or {}).get(
            "evidence_quality", "none"
        ),
    )


def _web_source_to_state(source: WebSourceResult) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": source.title,
        "url": source.url,
        "excerpt": source.excerpt,
        "provider": source.provider,
        "published_date": source.published_date,
    }


def _state_to_web_source(data: dict[str, Any]) -> WebSourceResult:
    return WebSourceResult(
        source_id=data["source_id"],
        title=data["title"],
        url=data["url"],
        excerpt=data["excerpt"],
        provider=data.get("provider", "deterministic"),
        published_date=data.get("published_date"),
    )


def _web_research_result_to_state(result: WebResearchResult) -> dict[str, Any]:
    sources = [_web_source_to_state(source) for source in result.sources]
    return {
        "web_summary": result.summary,
        "web_sources": sources,
        "web_results": {
            "summary": result.summary,
            "sources": sources,
            "status": result.status,
            "warnings": result.warnings,
            "errors": result.errors,
            "skipped": result.status == "skipped",
        },
        "warnings": result.warnings,
        "errors": result.errors,
    }


def _state_to_web_research_result(state: ChatRAGState) -> WebResearchResult | None:
    if (
        state.get("web_summary") is None
        and not state.get("web_sources")
        and state.get("web_results") is None
    ):
        return None

    return WebResearchResult(
        summary=state.get("web_summary"),
        sources=[
            _state_to_web_source(source) for source in state.get("web_sources", [])
        ],
        status=(state.get("web_results", {}) or {}).get("status", "available"),
        warnings=(state.get("web_results", {}) or {}).get("warnings", []),
        errors=(state.get("web_results", {}) or {}).get("errors", []),
    )


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            stripped = value.strip()
            if stripped and stripped not in seen:
                merged.append(stripped)
                seen.add(stripped)
    return merged


def _retrieved_chunk_response(
    chunk: dict[str, Any], citation: RagCitation
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk["chunk_id"],
        document_id=chunk["document_id"],
        document_title=chunk.get("document_title"),
        document_source_path=chunk.get("document_source_path"),
        chunk_index=chunk["chunk_index"],
        page_number=citation.page_number,
        page_start=chunk.get("page_start"),
        page_end=chunk.get("page_end"),
        section_type=chunk.get("section_type"),
        chapter_title=chunk.get("chapter_title"),
        section_title=chunk.get("section_title"),
        content=chunk["content"],
        char_start=chunk["char_start"],
        char_end=chunk["char_end"],
        score=chunk["score"],
        citation=citation,
    )
