import socket
import uuid

from app.agents.local_library import run_local_library_agent
from app.agents.router import route_question
from app.agents.synthesis import synthesize_agent_answer
from app.agents.web_research import run_web_research_agent
from app.rag.retrieval import RetrievedChunkResult


def test_router_routes_local_only_questions() -> None:
    assert route_question("According to my books, what is compactness?") == "local_only"
    assert route_question("根据我的资料解释线性空间") == "local_only"


def test_router_routes_web_only_questions() -> None:
    assert route_question("What is the latest news about topology?") == "web_only"
    assert route_question("最近网上有什么关于 AI 的消息？") == "web_only"


def test_router_routes_both_when_local_and_web_keywords_are_present() -> None:
    assert route_question("Use my PDFs and recent web context") == "both"


def test_router_defaults_uncertain_learning_questions_to_both() -> None:
    assert route_question("Explain the mean value theorem") == "both"


def test_local_library_agent_returns_citations_and_page_metadata() -> None:
    chunk = RetrievedChunkResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Analysis PDF",
        document_source_path="/tmp/analysis.pdf",
        library_item_id=uuid.uuid4(),
        library_title="Analysis",
        library_author="Author",
        chunk_index=2,
        content="The mean value theorem compares average and instantaneous change.",
        char_start=10,
        char_end=78,
        page_start=12,
        page_end=12,
        score=0.05,
    )

    result = run_local_library_agent(
        None,  # type: ignore[arg-type]
        question="What does my library say about the mean value theorem?",
        scope_type="global",
        library_item_id=None,
        library_item_ids=[],
        top_k=3,
        retrieve_global=lambda session, question, top_k: [chunk],
    )

    assert result.summary.startswith("This is a minimal MVP answer")
    assert result.retrieved_chunks == [chunk]
    assert result.citations[0].library_title == "Analysis"
    assert result.citations[0].page_number == 12
    assert result.citations[0].page_start == 12
    assert result.citations[0].page_end == 12


def test_web_research_agent_is_deterministic_without_network(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("deterministic web research must not open network sockets")

    monkeypatch.setattr(socket, "socket", fail_if_called)

    result = run_web_research_agent("What is the latest update?")

    assert "No live network request was made" in result.summary
    assert result.sources[0].source_id == "W1"
    assert result.sources[0].provider == "deterministic"
    assert result.sources[0].url.startswith("mock://")


def test_synthesis_handles_local_only() -> None:
    local_result = run_local_library_agent(
        None,  # type: ignore[arg-type]
        question="Use my books",
        scope_type="global",
        library_item_id=None,
        library_item_ids=[],
        top_k=1,
        retrieve_global=lambda session, question, top_k: [],
    )

    result = synthesize_agent_answer(
        question="Use my books",
        route="local_only",
        local_result=local_result,
    )

    assert result.answer == local_result.summary
    assert result.local_summary == local_result.summary
    assert result.web_summary is None


def test_synthesis_handles_web_only() -> None:
    web_result = run_web_research_agent("What is current?")

    result = synthesize_agent_answer(
        question="What is current?",
        route="web_only",
        web_result=web_result,
    )

    assert result.answer == web_result.summary
    assert result.local_summary is None
    assert result.web_summary == web_result.summary


def test_synthesis_handles_both() -> None:
    local_result = run_local_library_agent(
        None,  # type: ignore[arg-type]
        question="Explain derivatives",
        scope_type="global",
        library_item_id=None,
        library_item_ids=[],
        top_k=1,
        retrieve_global=lambda session, question, top_k: [],
    )
    web_result = run_web_research_agent("Explain derivatives")

    result = synthesize_agent_answer(
        question="Explain derivatives",
        route="both",
        local_result=local_result,
        web_result=web_result,
    )

    assert local_result.summary in result.answer
    assert f"Web research: {web_result.summary}" in result.answer
    assert result.local_summary == local_result.summary
    assert result.web_summary == web_result.summary
