import uuid
import asyncio
import json
import logging
from functools import partial
from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import Annotated, Any, TypedDict

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
from app.llm.providers import (
    DETERMINISTIC_ANSWER_MARKER,
    LLMProviderError,
    TokenUsage,
    get_llm_provider,
)
from app.memory.long_term import (
    LongTermMemoryResult,
)
from app.mcp.gateway import MCPToolGateway
from app.mcp.research import (
    run_mcp_academic_research,
    run_mcp_web_research,
)
from app.mcp.client import mcp_client_manager
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
from app.graphs.adaptive import (
    EvidenceGrade,
    EvidenceItem,
    ExecutionPlan,
    QueryAnalysis,
    analyze_query,
    build_answer_plan,
    build_execution_plan,
    grade_evidence,
    merge_evidence,
    repair_answer_citations,
    verify_answer,
)

logger = logging.getLogger(__name__)


class ChatRAGGraphError(ValueError):
    """Raised when the Chat RAG graph cannot complete."""


class ChatRAGValidationError(ChatRAGGraphError):
    """Raised when the graph input is invalid."""


def _reduce_unique_values(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


class AgentGraphState(TypedDict, total=False):
    # Stable graph contract for the dual-agent MVP. Values are kept JSON-like
    # because LangGraph passes state between independent node functions.
    user_message: str
    selected_library_item_ids: list[str]
    settings: dict[str, Any]
    route_decision: AgentRoute
    query_analysis: dict[str, Any]
    execution_plan: dict[str, Any]
    subqueries: list[str]
    local_results: dict[str, Any] | None
    web_results: dict[str, Any] | None
    academic_results: dict[str, Any] | None
    local_evidence: list[dict[str, Any]]
    web_evidence: list[dict[str, Any]]
    academic_evidence: list[dict[str, Any]]
    merged_evidence: list[dict[str, Any]]
    evidence_grade: dict[str, Any]
    retrieval_retry_count: int
    answer_plan: dict[str, Any]
    verification_result: dict[str, Any]
    answer_repair_count: int
    final_answer: str
    local_citations: list[dict[str, Any]]
    web_sources: list[dict[str, Any]]
    academic_sources: list[dict[str, Any]]
    warnings: Annotated[list[str], _reduce_unique_values]
    errors: Annotated[list[str], _reduce_unique_values]
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
    """Build the controlled adaptive research graph."""
    graph = StateGraph(AgentGraphState)
    gateway = MCPToolGateway()

    graph.add_node("validate_input", validate_input)
    graph.add_node("resolve_scope", lambda state: resolve_scope(state, session))
    graph.add_node("load_memory", lambda state: load_memory(state, session))
    graph.add_node("analyze_query", analyze_query_node)
    graph.add_node("build_execution_plan", build_execution_plan_node)
    graph.add_node(
        "local_research",
        lambda state: run_local_node_with_independent_session(state, session),
    )
    graph.add_node(
        "web_research", lambda state: web_research_agent_node(state, gateway=gateway)
    )
    graph.add_node(
        "academic_research",
        lambda state: academic_research_agent_node(state, gateway=gateway),
    )
    graph.add_node("merge_evidence", merge_evidence_node)
    graph.add_node("grade_evidence", grade_evidence_node)
    graph.add_node(
        "corrective_retrieval",
        lambda state: corrective_retrieval_node(
            state, session=session, gateway=gateway
        ),
    )
    graph.add_node("build_answer_plan", build_answer_plan_node)
    graph.add_node("stream_synthesis", synthesis_node)
    graph.add_node("verify_answer", verify_answer_node)
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
    graph.add_edge("load_memory", "analyze_query")
    graph.add_edge("analyze_query", "build_execution_plan")
    graph.add_edge("build_execution_plan", "local_research")
    graph.add_edge("build_execution_plan", "web_research")
    graph.add_edge("build_execution_plan", "academic_research")
    graph.add_edge(
        ["local_research", "web_research", "academic_research"], "merge_evidence"
    )
    graph.add_edge("merge_evidence", "grade_evidence")
    graph.add_conditional_edges(
        "grade_evidence",
        corrective_route,
        {"correct": "corrective_retrieval", "answer": "build_answer_plan"},
    )
    graph.add_edge("corrective_retrieval", "merge_evidence")
    graph.add_edge("build_answer_plan", "stream_synthesis")
    graph.add_edge("stream_synthesis", "verify_answer")
    graph.add_edge("verify_answer", "save_memory")
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
    """Build the async SSE form of the controlled adaptive research graph."""
    graph = StateGraph(AgentGraphState)
    gateway = MCPToolGateway()
    graph.add_node("validate_input", validate_input)
    graph.add_node(
        "resolve_scope",
        lambda state: streaming_resolve_scope_node(state, session_factory),
    )
    graph.add_node(
        "load_memory",
        lambda state: streaming_load_memory_node(state, session_factory),
    )
    graph.add_node("analyze_query", streaming_analyze_query_node)
    graph.add_node("build_execution_plan", streaming_execution_plan_node)
    graph.add_node(
        "local_research",
        lambda state: streaming_local_node(state, session_factory),
    )
    graph.add_node("web_research", partial(streaming_web_node, gateway=gateway))
    graph.add_node(
        "academic_research",
        partial(streaming_academic_node, gateway=gateway),
    )
    graph.add_node("merge_evidence", streaming_merge_evidence_node)
    graph.add_node("grade_evidence", streaming_grade_evidence_node)
    graph.add_node(
        "corrective_retrieval",
        partial(
            streaming_corrective_retrieval_node,
            session_factory=session_factory,
            gateway=gateway,
        ),
    )
    graph.add_node("build_answer_plan", streaming_answer_plan_node)
    graph.add_node("stream_synthesis", streaming_synthesis_node)
    graph.add_node("verify_answer", streaming_verify_answer_node)
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
    graph.add_edge("load_memory", "analyze_query")
    graph.add_edge("analyze_query", "build_execution_plan")
    graph.add_edge("build_execution_plan", "local_research")
    graph.add_edge("build_execution_plan", "web_research")
    graph.add_edge("build_execution_plan", "academic_research")
    graph.add_edge(
        ["local_research", "web_research", "academic_research"], "merge_evidence"
    )
    graph.add_edge("merge_evidence", "grade_evidence")
    graph.add_conditional_edges(
        "grade_evidence",
        corrective_route,
        {"correct": "corrective_retrieval", "answer": "build_answer_plan"},
    )
    graph.add_edge("corrective_retrieval", "merge_evidence")
    graph.add_edge("build_answer_plan", "stream_synthesis")
    graph.add_edge("stream_synthesis", "verify_answer")
    graph.add_edge("verify_answer", "persist_final")
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


def analyze_query_node(state: ChatRAGState) -> ChatRAGState:
    settings = get_settings()
    with measure_latency_sync("query_analysis"):
        analysis = analyze_query(
            state["question"],
            selected_book_count=len(state.get("selected_library_items", [])),
            has_conversation_context=bool(
                state.get("short_term_context") or state.get("conversation_summary")
            ),
            provider=get_llm_provider(),
            provider_name=settings.llm_provider,
        )
    return {"query_analysis": analysis.model_dump(), "subqueries": analysis.subqueries}


async def streaming_analyze_query_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("understanding_query", "正在理解问题")
    return await asyncio.to_thread(analyze_query_node, state)


def build_execution_plan_node(state: ChatRAGState) -> ChatRAGState:
    analysis = QueryAnalysis.model_validate(state["query_analysis"])
    with measure_latency_sync("planning"):
        plan = build_execution_plan(analysis)
    trace = current_latency_trace()
    if trace is not None:
        trace.route = plan.route
        trace.set_counter("route", plan.route)
        trace.set_counter("execution_mode", plan.mode)
        trace.set_counter(
            "selected_library_item_count",
            len(state.get("selected_library_items", [])),
        )
    return {
        "execution_plan": plan.model_dump(),
        "route": plan.route,
        "route_decision": plan.route,
    }


def streaming_execution_plan_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("planning_research", "正在制定检索计划")
    result = build_execution_plan_node(state)
    _write_custom({"kind": "route_selected", "route": result["route"]})
    return result


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
        if not _should_run(state, "local"):
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


async def streaming_web_node(
    state: ChatRAGState, *, gateway: MCPToolGateway | None = None
) -> ChatRAGState:
    if not _should_run(state, "web"):
        return _skipped_web_state()
    settings = get_settings()
    if settings.mcp_enabled:
        result = await mcp_web_research_agent_node(state, gateway=gateway)
    else:
        _write_activity("searching_web", "正在搜索网络资料")
        result = await asyncio.to_thread(web_research_agent_node, state)
    _write_custom(
        {
            "kind": "retrieval_completed",
            "source": "web",
            "result_count": len(result.get("web_sources", [])),
        }
    )
    return result


async def mcp_web_research_agent_node(
    state: ChatRAGState, *, gateway: MCPToolGateway | None = None
) -> ChatRAGState:
    trace = current_latency_trace()
    if trace is not None:
        trace.increment("web_search_call_count")
    with measure_latency_sync("web_subgraph"):
        result = await run_mcp_web_research(
            _research_query(state),
            gateway=gateway or MCPToolGateway(),
            activity=_write_activity,
        )
        with measure_latency_sync("web_result_processing"):
            result_state = _web_research_result_to_state(result)
    if trace is not None:
        trace.set_counter("web_result_count", len(result.sources))
    return result_state


async def streaming_academic_node(
    state: ChatRAGState, *, gateway: MCPToolGateway | None = None
) -> ChatRAGState:
    if not _should_run(state, "academic"):
        return _skipped_academic_state()
    _write_activity("searching_academic", "正在搜索学术资料")
    result = await _run_academic_async(state, gateway or MCPToolGateway())
    _write_custom(
        {
            "kind": "retrieval_completed",
            "source": "academic",
            "result_count": len(result.get("academic_sources", [])),
        }
    )
    return result


def streaming_merge_evidence_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("evaluating_sources", "正在评估来源")
    return merge_evidence_node(state)


def streaming_grade_evidence_node(state: ChatRAGState) -> ChatRAGState:
    return grade_evidence_node(state)


async def streaming_corrective_retrieval_node(
    state: ChatRAGState,
    *,
    session_factory: Callable[[], Session],
    gateway: MCPToolGateway,
) -> ChatRAGState:
    _write_activity("correcting_retrieval", "正在补充资料")
    session = session_factory()
    try:
        return await corrective_retrieval_async(state, session=session, gateway=gateway)
    finally:
        session.rollback()
        session.close()


def streaming_answer_plan_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("organizing_answer", "正在组织回答")
    return build_answer_plan_node(state)


def streaming_verify_answer_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("verifying_citations", "正在验证引用")
    return verify_answer_node(state)


async def streaming_synthesis_node(state: ChatRAGState) -> ChatRAGState:
    _write_activity("processing_sources", "正在整合本地与网络证据")
    execution_plan = ExecutionPlan.model_validate(state["execution_plan"])
    if execution_plan.clarification_question:
        answer = execution_plan.clarification_question
        _write_activity("streaming", "正在生成回答")
        _write_custom({"kind": "synthesis_token", "delta": answer})
        return {"answer": answer, "final_answer": answer}
    if execution_plan.mode == "direct_answer":
        prompt = _direct_answer_prompt(state["question"])
        local_summary = None
        web_summary = None
        prepared_warnings: list[str] = []
        prepared_errors: list[str] = []
    else:
        local_result = _state_to_local_library_agent_result(state)
        web_result = _state_to_web_research_result(state)
        prepared = prepare_agent_synthesis(
            question=state["question"],
            route=state["route"],
            local_result=local_result,
            web_result=web_result,
            memory_context=state.get("memory_prompt_context", ""),
            answer_plan=json.dumps(state.get("answer_plan", {}), ensure_ascii=False),
        )
        prompt = prepared.prompt
        local_summary = prepared.local_summary
        web_summary = prepared.web_summary
        prepared_warnings = prepared.warnings
        prepared_errors = prepared.errors
    _write_activity("synthesizing", "正在生成回答")
    provider = get_llm_provider()
    started_at = perf_counter()
    first_token_at: float | None = None
    last_token_at: float | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    chunks: list[str] = []
    async for chunk in provider.stream_chat_completion(prompt):
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
        "local_summary": local_summary,
        "web_summary": web_summary,
        "warnings": _merge_unique_strings(state.get("warnings", []), prepared_warnings),
        "errors": _merge_unique_strings(state.get("errors", []), prepared_errors),
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
    settings = get_settings()
    return {
        "user_message": request.question or request.message or "",
        "selected_library_item_ids": selected_library_item_ids,
        "settings": {
            "mcp_enabled": settings.mcp_enabled,
            "mcp_max_calls_per_request": settings.mcp_max_calls_per_request,
            "mcp_max_evidence": settings.mcp_max_evidence,
            "mcp_max_fetch_urls": settings.mcp_max_fetch_urls,
        },
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
        "academic_sources": [],
        "local_citations": [],
        "query_analysis": {},
        "execution_plan": {},
        "subqueries": [],
        "local_evidence": [],
        "web_evidence": [],
        "academic_evidence": [],
        "merged_evidence": [],
        "evidence_grade": {},
        "retrieval_retry_count": 0,
        "answer_plan": {},
        "verification_result": {},
        "answer_repair_count": 0,
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
    if not _should_run(state, "local"):
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
    with measure_latency_sync("local_subgraph"):
        with measure_latency_sync("local_agent_total"):
            result = run_local_library_agent_service(
                session,
                question=_research_query(state),
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


def web_research_agent_node(
    state: ChatRAGState, *, gateway: MCPToolGateway | None = None
) -> ChatRAGState:
    # The web agent is provider-backed and always returns structured [W#] sources.
    if not _should_run(state, "web"):
        return _skipped_web_state()

    trace = current_latency_trace()
    if trace is not None:
        trace.increment("web_search_call_count")
        if get_settings().web_research_provider.strip().lower() == "tavily":
            trace.increment("tavily_call_count")
    settings = get_settings()
    if settings.mcp_enabled:
        with measure_latency_sync("web_subgraph"):
            result = mcp_client_manager.run_sync(
                run_mcp_web_research(
                    _research_query(state), gateway=gateway or MCPToolGateway()
                ),
                timeout_seconds=(settings.mcp_total_timeout_seconds),
            )
            with measure_latency_sync("web_result_processing"):
                result_state = _web_research_result_to_state(result)
        if trace is not None:
            trace.set_counter("web_result_count", len(result.sources))
        return result_state
    with measure_latency_sync("web_subgraph"):
        with measure_latency_sync("web_search"):
            result = run_web_research_agent_service(state["question"])
        with measure_latency_sync("web_result_processing"):
            result_state = _web_research_result_to_state(result)
    if trace is not None:
        trace.set_counter("web_result_count", len(result.sources))
    return result_state


def academic_research_agent_node(
    state: ChatRAGState, *, gateway: MCPToolGateway | None = None
) -> ChatRAGState:
    if not _should_run(state, "academic"):
        return _skipped_academic_state()
    settings = get_settings()
    if not settings.mcp_enabled:
        return {
            **_skipped_academic_state(),
            "warnings": ["Academic MCP research is not enabled."],
        }
    with measure_latency_sync("academic_subgraph"):
        result = mcp_client_manager.run_sync(
            run_mcp_academic_research(
                _research_query(state), gateway=gateway or MCPToolGateway()
            ),
            timeout_seconds=settings.mcp_total_timeout_seconds,
        )
    return _academic_result_to_state(result)


def merge_evidence_node(state: ChatRAGState) -> ChatRAGState:
    with measure_latency_sync("evidence_merge"):
        local_chunks, local_citations = _dedupe_local_sources(state)
        local = _local_evidence_from_state(
            {
                **state,
                "retrieved_chunks": local_chunks,
                "local_citations": local_citations,
            }
        )
        combined_sources = _renumber_web_sources(
            [*state.get("web_sources", []), *state.get("academic_sources", [])]
        )
        web_source_items = [
            item for item in combined_sources if item.get("source_type") != "academic"
        ]
        academic_source_items = [
            item for item in combined_sources if item.get("source_type") == "academic"
        ]
        web = _web_evidence_from_sources(web_source_items, "web")
        academic = _web_evidence_from_sources(academic_source_items, "academic")
        merged = merge_evidence([*local, *web, *academic])
        combined_result = _combined_web_result_state(state, combined_sources)
    trace = current_latency_trace()
    if trace is not None:
        trace.set_counter("evidence_count", len(merged))
    return {
        "local_evidence": [item.model_dump() for item in local],
        "web_evidence": [item.model_dump() for item in web],
        "academic_evidence": [item.model_dump() for item in academic],
        "merged_evidence": [item.model_dump() for item in merged],
        "retrieved_chunks": local_chunks,
        "citations": local_citations,
        "local_citations": local_citations,
        "web_sources": combined_sources,
        "web_summary": combined_result["summary"],
        "web_results": combined_result,
    }


def grade_evidence_node(state: ChatRAGState) -> ChatRAGState:
    analysis = QueryAnalysis.model_validate(state["query_analysis"])
    evidence = [
        EvidenceItem.model_validate(item) for item in state.get("merged_evidence", [])
    ]
    with measure_latency_sync("evidence_grade"):
        grade = grade_evidence(state["question"], analysis, evidence)
    return {"evidence_grade": grade.model_dump()}


def corrective_route(state: ChatRAGState) -> str:
    grade = EvidenceGrade.model_validate(state["evidence_grade"])
    plan = ExecutionPlan.model_validate(state["execution_plan"])
    count = state.get("retrieval_retry_count", 0)
    external_unavailable = (
        plan.run_web
        and (state.get("web_results") or {}).get("status") == "unavailable"
        and not get_settings().mcp_enabled
    )
    if external_unavailable and not state.get("retrieved_chunks"):
        return "answer"
    needs_correction = grade.status == "empty" or (
        grade.status == "insufficient" and grade.relevance < 0.3
    )
    if needs_correction and count < plan.max_corrective_retries:
        return "correct"
    return "answer"


def corrective_retrieval_node(
    state: ChatRAGState, *, session: Session, gateway: MCPToolGateway
) -> ChatRAGState:
    if not get_settings().mcp_enabled:
        plan = ExecutionPlan.model_validate(state["execution_plan"])
        retry_count = state.get("retrieval_retry_count", 0) + 1
        trace = current_latency_trace()
        if trace is not None:
            trace.increment("corrective_retry_count")
        correction_state = {
            **state,
            "subqueries": [_corrective_query(state)],
            "top_k": min(20, state["top_k"] * 2),
        }
        updates: dict[str, Any] = {"retrieval_retry_count": retry_count}
        if plan.run_local:
            updates.update(
                run_local_node_with_independent_session(correction_state, session)
            )
        if plan.run_web:
            updates.update(web_research_agent_node(correction_state, gateway=gateway))
        if plan.run_academic:
            updates.update(_skipped_academic_state())
            updates["warnings"] = ["Academic MCP research is not enabled."]
        return _preserve_prior_evidence(state, updates)
    return mcp_client_manager.run_sync(
        corrective_retrieval_async(state, session=session, gateway=gateway),
        timeout_seconds=get_settings().mcp_total_timeout_seconds,
    )


async def corrective_retrieval_async(
    state: ChatRAGState, *, session: Session, gateway: MCPToolGateway
) -> ChatRAGState:
    plan = ExecutionPlan.model_validate(state["execution_plan"])
    retry_count = state.get("retrieval_retry_count", 0) + 1
    trace = current_latency_trace()
    if trace is not None:
        trace.increment("corrective_retry_count")
    query = _corrective_query(state)
    correction_state = {
        **state,
        "subqueries": [query],
        "top_k": min(20, state["top_k"] * 2),
    }
    updates: dict[str, Any] = {"retrieval_retry_count": retry_count}
    tasks: list[tuple[str, Any]] = []
    if plan.run_local:
        tasks.append(
            (
                "local",
                asyncio.to_thread(
                    run_local_node_with_independent_session, correction_state, session
                ),
            )
        )
    if plan.run_web:
        tasks.append(("web", streaming_web_node(correction_state, gateway=gateway)))
    if plan.run_academic:
        tasks.append(("academic", _run_academic_async(correction_state, gateway)))
    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    for (source, _), result in zip(tasks, results, strict=True):
        if isinstance(result, BaseException):
            updates["warnings"] = _merge_unique_strings(
                updates.get("warnings", []),
                [f"Corrective {source} retrieval was unavailable."],
            )
            continue
        updates.update(result)
    return _preserve_prior_evidence(state, updates)


def build_answer_plan_node(state: ChatRAGState) -> ChatRAGState:
    analysis = QueryAnalysis.model_validate(state["query_analysis"])
    grade = EvidenceGrade.model_validate(state["evidence_grade"])
    evidence = [
        EvidenceItem.model_validate(item) for item in state.get("merged_evidence", [])
    ]
    with measure_latency_sync("answer_plan"):
        plan = build_answer_plan(analysis, grade, evidence)
    warnings = list(state.get("warnings", []))
    if grade.status != "sufficient":
        warnings = _merge_unique_strings(
            warnings,
            ["The answer is based on incomplete or conflicting available evidence."],
        )
    return {"answer_plan": plan.model_dump(), "warnings": warnings}


def verify_answer_node(state: ChatRAGState) -> ChatRAGState:
    with measure_latency_sync("citation_verify"):
        result = verify_answer(
            state["answer"],
            state.get("local_citations", []),
            state.get("web_sources", []),
        )
        answer = state["answer"]
        repair_count = 0
        if not result.valid:
            answer = repair_answer_citations(
                answer,
                state.get("local_citations", []),
                state.get("web_sources", []),
            )
            repair_count = 1
            result = verify_answer(
                answer,
                state.get("local_citations", []),
                state.get("web_sources", []),
            ).model_copy(update={"repaired": True})
    trace = current_latency_trace()
    if trace is not None and repair_count:
        trace.increment("answer_repair_count")
    return {
        "answer": answer,
        "final_answer": answer,
        "verification_result": result.model_dump(),
        "answer_repair_count": repair_count,
        "warnings": _merge_unique_strings(
            state.get("warnings", []), result.warnings, result.errors
        ),
    }


def synthesis_node(state: ChatRAGState) -> ChatRAGState:
    # Synthesis combines agent outputs without merging local citations and web sources.
    execution_plan = ExecutionPlan.model_validate(state["execution_plan"])
    if execution_plan.clarification_question:
        return {
            "answer": execution_plan.clarification_question,
            "final_answer": execution_plan.clarification_question,
        }
    if execution_plan.mode == "direct_answer":
        provider = get_llm_provider()
        with measure_latency_sync("synthesis_total"):
            answer = provider.generate(_direct_answer_prompt(state["question"]))
        return {"answer": answer, "final_answer": answer}
    local_result = _state_to_local_library_agent_result(state)
    web_result = _state_to_web_research_result(state)
    synthesis = synthesize_agent_answer(
        question=state["question"],
        route=state["route"],
        local_result=local_result,
        web_result=web_result,
        llm_provider=get_llm_provider(),
        memory_context=state.get("memory_prompt_context", ""),
        answer_plan=json.dumps(state.get("answer_plan", {}), ensure_ascii=False),
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


def _direct_answer_prompt(question: str) -> str:
    return "\n".join(
        [
            "Respond briefly to this simple request without research or citations.",
            f"User request: {question.strip()}",
            "",
            DETERMINISTIC_ANSWER_MARKER,
            "Hello! How can I help with your learning today?",
        ]
    )


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
        "extraction_method": chunk.extraction_method,
        "ocr_confidence": chunk.ocr_confidence,
        "section_path": list(chunk.section_path),
        "bounding_boxes": list(chunk.bounding_boxes),
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
        extraction_method=data.get("extraction_method", "text"),
        ocr_confidence=data.get("ocr_confidence"),
        section_path=tuple(data.get("section_path", [])),
        bounding_boxes=tuple(data.get("bounding_boxes", [])),
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
        "source_type": citation.source_type,
        "title": citation.title,
        "section_path": list(citation.section_path),
        "extraction_method": citation.extraction_method,
        "ocr_confidence": citation.ocr_confidence,
        "bounding_boxes": list(citation.bounding_boxes),
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
        source_type=data.get("source_type", "local"),
        title=data.get("title"),
        section_path=tuple(data.get("section_path", [])),
        extraction_method=data.get("extraction_method"),
        ocr_confidence=data.get("ocr_confidence"),
        bounding_boxes=tuple(data.get("bounding_boxes", [])),
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
        "citation_id": source.source_id,
        "title": source.title,
        "url": source.url,
        "excerpt": source.excerpt,
        "provider": source.provider,
        "published_date": source.published_date,
        "published_at": source.published_at,
        "retrieved_at": source.retrieved_at,
        "evidence_id": source.evidence_id,
        "source_type": source.source_type,
        "content": source.content,
        "authors": list(source.authors),
        "doi": source.doi,
        "arxiv_id": source.arxiv_id,
    }


def _state_to_web_source(data: dict[str, Any]) -> WebSourceResult:
    return WebSourceResult(
        source_id=data["source_id"],
        title=data["title"],
        url=data["url"],
        excerpt=data["excerpt"],
        provider=data.get("provider", "deterministic"),
        published_date=data.get("published_date"),
        published_at=data.get("published_at"),
        retrieved_at=data.get("retrieved_at"),
        evidence_id=data.get("evidence_id"),
        source_type=data.get("source_type", "web"),
        content=data.get("content"),
        authors=tuple(data.get("authors", [])),
        doi=data.get("doi"),
        arxiv_id=data.get("arxiv_id"),
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


def _should_run(state: ChatRAGState, source: str) -> bool:
    raw = state.get("execution_plan")
    if raw:
        plan = ExecutionPlan.model_validate(raw)
        return {
            "local": plan.run_local,
            "web": plan.run_web,
            "academic": plan.run_academic,
        }[source]
    route = state.get("route", "both")
    return (
        source == "local"
        and route != "web_only"
        or source == "web"
        and route != "local_only"
    )


def _research_query(state: ChatRAGState) -> str:
    subqueries = state.get("subqueries", [])
    return subqueries[0] if subqueries else state["question"]


def _corrective_query(state: ChatRAGState) -> str:
    grade = EvidenceGrade.model_validate(state["evidence_grade"])
    missing = ", ".join(grade.missing_aspects) or "missing supporting evidence"
    return f"{state['question']} Focus on: {missing}."


def _skipped_web_state() -> ChatRAGState:
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


def _skipped_academic_state() -> ChatRAGState:
    return {
        "academic_sources": [],
        "academic_results": {
            "summary": None,
            "sources": [],
            "status": "skipped",
            "warnings": [],
            "errors": [],
            "skipped": True,
        },
    }


async def _run_academic_async(
    state: ChatRAGState, gateway: MCPToolGateway
) -> ChatRAGState:
    settings = get_settings()
    if not settings.mcp_enabled:
        return {
            **_skipped_academic_state(),
            "warnings": ["Academic MCP research is not enabled."],
        }
    with measure_latency_sync("academic_subgraph"):
        result = await run_mcp_academic_research(
            _research_query(state), gateway=gateway, activity=_write_activity
        )
    return _academic_result_to_state(result)


def _academic_result_to_state(result: WebResearchResult) -> ChatRAGState:
    sources = [
        {**_web_source_to_state(source), "source_type": "academic"}
        for source in result.sources
    ]
    return {
        "academic_sources": sources,
        "academic_results": {
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


def _local_evidence_from_state(state: ChatRAGState) -> list[EvidenceItem]:
    chunks = state.get("retrieved_chunks", [])
    citations = state.get("local_citations", state.get("citations", []))
    items: list[EvidenceItem] = []
    for chunk, citation in zip(chunks, citations, strict=False):
        citation_id = str(citation.get("citation_id", ""))
        items.append(
            EvidenceItem(
                evidence_id=f"local:{chunk.get('chunk_id', citation_id)}",
                source="local",
                title=str(
                    citation.get("library_title")
                    or citation.get("document_title")
                    or "Local Library"
                ),
                excerpt=str(chunk.get("content", ""))[:4_000],
                citation_id=citation_id,
                library_item_id=citation.get("library_item_id"),
                page_start=citation.get("page_start"),
                page_end=citation.get("page_end"),
            )
        )
    return items


def _dedupe_local_sources(
    state: ChatRAGState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_citations = state.get("local_citations", state.get("citations", []))
    for chunk, citation in zip(
        state.get("retrieved_chunks", []), source_citations, strict=False
    ):
        key = str(chunk.get("chunk_id") or citation.get("chunk_id"))
        if key in seen:
            continue
        seen.add(key)
        identifier = f"S{len(chunks) + 1}"
        chunks.append(chunk)
        citations.append({**citation, "citation_id": identifier})
    return chunks, citations


def _web_evidence_from_sources(
    sources: list[dict[str, Any]], source: str
) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            evidence_id=str(item.get("evidence_id") or item.get("source_id")),
            source=source,  # type: ignore[arg-type]
            title=str(item.get("title", "Untitled source")),
            excerpt=str(item.get("content") or item.get("excerpt") or "")[:4_000],
            citation_id=str(item.get("source_id", "")),
            url=item.get("url"),
            provider=item.get("provider"),
            published_at=item.get("published_at") or item.get("published_date"),
            authors=list(item.get("authors", [])),
            doi=item.get("doi"),
            arxiv_id=item.get("arxiv_id"),
        )
        for item in sources
    ]


def _renumber_web_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        doi = str(source.get("doi") or "").lower().removeprefix("https://doi.org/")
        arxiv_id = str(source.get("arxiv_id") or "").lower().removeprefix("arxiv:")
        key = str(
            (f"doi:{doi}" if doi else None)
            or (f"arxiv:{arxiv_id}" if arxiv_id else None)
            or source.get("url")
            or source.get("evidence_id")
            or source.get("title")
        )
        key = key.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        citation_id = f"W{len(result) + 1}"
        result.append({**source, "source_id": citation_id, "citation_id": citation_id})
    return result


def _combined_web_result_state(
    state: ChatRAGState, sources: list[dict[str, Any]]
) -> dict[str, Any]:
    web = state.get("web_results") or {}
    academic = state.get("academic_results") or {}
    summary = " ".join(
        f"[{source.get('source_id')}] {source.get('title')}: "
        f"{str(source.get('content') or source.get('excerpt') or '')[:500]}"
        for source in sources
    )
    return {
        "summary": summary or None,
        "sources": sources,
        "status": "available" if sources else "unavailable",
        "warnings": _merge_unique_strings(
            web.get("warnings", []), academic.get("warnings", [])
        ),
        "errors": _merge_unique_strings(
            web.get("errors", []), academic.get("errors", [])
        ),
        "skipped": not sources,
    }


def _preserve_prior_evidence(
    state: ChatRAGState, updates: dict[str, Any]
) -> dict[str, Any]:
    for key in ("retrieved_chunks", "citations", "local_citations"):
        if key in updates:
            existing = state.get(key, [])
            updates[key] = [*existing, *updates[key]]
    for key in ("web_sources", "academic_sources"):
        if key in updates:
            updates[key] = [*state.get(key, []), *updates[key]]
    return updates


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
