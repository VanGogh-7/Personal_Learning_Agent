import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.embeddings.base import EMBEDDING_DIMENSION
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.library_item import LibraryItem
from scripts.ask_book import ask_book
from scripts.eval_retrieval import evaluate_retrieval
from scripts.eval_retrieval import load_eval_queries
from scripts.eval_retrieval import main as eval_retrieval_main
from scripts.index_pdf import index_pdf_file
from scripts.search_book import main as search_book_main
from scripts.search_book import search_book
from tests.pdf_fixtures import make_pdf_bytes


def _create_script_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    LibraryItem.metadata.create_all(
        engine,
        tables=[LibraryItem.__table__, Document.__table__, DocumentChunk.__table__],
    )
    session = Session(engine)
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


def _close_script_session(session: Session) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    session.close()
    engine.dispose()


def test_index_pdf_script_indexes_pdf_and_preserves_page_metadata(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "Complete metric spaces are central in analysis.",
                    "",
                    "Banach spaces are complete normed vector spaces.",
                ]
            )
        )

        summary = index_pdf_file(pdf_path, session=session)

        assert summary.chunk_count == 2
        assert summary.embedding_provider == "mock"
        assert summary.embedding_dimension == EMBEDDING_DIMENSION
        assert summary.empty_page_count == 1

        item = session.get(LibraryItem, summary.library_item_id)
        assert item is not None
        assert item.file_type == "pdf"
        assert item.status == "indexed"

        document = session.get(Document, summary.document_id)
        assert document is not None
        assert document.library_item_id == summary.library_item_id
        assert document.file_path == str(pdf_path.resolve())

        chunks = session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == summary.document_id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars().all()
        assert [chunk.page_start for chunk in chunks] == [1, 3]
        assert [chunk.page_end for chunk in chunks] == [1, 3]
        assert all(chunk.embedding is not None for chunk in chunks)
        assert all(len(chunk.embedding) == EMBEDDING_DIMENSION for chunk in chunks)
    finally:
        _close_script_session(session)


def test_index_pdf_script_reuses_library_item_for_same_path(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(make_pdf_bytes(["Compactness has many equivalent forms."]))

        first = index_pdf_file(pdf_path, session=session)
        second = index_pdf_file(pdf_path, session=session)

        assert second.library_item_id == first.library_item_id
        assert second.document_id == first.document_id
        items = session.execute(select(LibraryItem)).scalars().all()
        assert len(items) == 1
    finally:
        _close_script_session(session)


def test_ask_book_script_runs_single_book_rag_with_citations(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "functional-analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "A Banach space is a complete normed vector space.",
                    "A complete metric space is one where every Cauchy sequence converges.",
                ]
            )
        )
        indexed = index_pdf_file(pdf_path, session=session)

        summary = ask_book(
            "What does the book say about Banach spaces?",
            library_item_id=indexed.library_item_id,
            top_k=2,
            session=session,
        )

        assert summary.library_item_id == indexed.library_item_id
        assert summary.answer
        assert len(summary.citations) == 2
        assert {citation.library_item_id for citation in summary.citations} == {
            str(indexed.library_item_id)
        }
        assert {citation.document_id for citation in summary.citations} == {
            str(indexed.document_id)
        }
        assert {citation.page_number for citation in summary.citations} == {1, 2}
        assert all(citation.excerpt for citation in summary.citations)
    finally:
        _close_script_session(session)


def test_search_book_script_runs_retrieval_without_answer_generation(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "metric-spaces.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "Complete metric spaces make Cauchy sequences converge.",
                    "Banach spaces are complete normed vector spaces.",
                    "Compactness in metric spaces has sequential characterizations.",
                ]
            )
        )
        indexed = index_pdf_file(pdf_path, session=session)
        indexed_chunks = session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == indexed.document_id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars().all()
        indexed_chunks[0].section_type = "index"
        session.flush()

        summary = search_book(
            "complete metric spaces",
            library_item_id=indexed.library_item_id,
            top_k=3,
            session=session,
        )
        unfiltered_summary = search_book(
            "complete metric spaces",
            library_item_id=indexed.library_item_id,
            top_k=3,
            include_non_body=True,
            session=session,
        )

        assert summary.library_item_id == indexed.library_item_id
        assert summary.query == "complete metric spaces"
        assert len(summary.chunks) == 2
        assert {chunk.section_type for chunk in summary.chunks} == {"body"}
        assert len(unfiltered_summary.chunks) == 3
        assert "index" in {chunk.section_type for chunk in unfiltered_summary.chunks}
        assert all(chunk.score >= 0 for chunk in summary.chunks)
        assert {chunk.library_title for chunk in summary.chunks} == {"metric-spaces"}
        assert {chunk.page_start for chunk in summary.chunks}.issubset({1, 2, 3})
    finally:
        _close_script_session(session)


def test_search_book_cli_prints_ranked_chunks(tmp_path, capsys, monkeypatch) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "functional-analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(["A Banach space is a complete normed vector space."])
        )
        indexed = index_pdf_file(pdf_path, session=session)

        monkeypatch.setattr("scripts.search_book.get_db_session", lambda: session)

        exit_code = search_book_main(
            [
                "--library-item-id",
                str(indexed.library_item_id),
                "--top-k",
                "1",
                "--max-snippet-chars",
                "40",
                "Banach spaces",
            ]
        )

        output = capsys.readouterr().out
        assert exit_code == 0
        assert "Retrieved chunks:" in output
        assert "1. functional-analysis" in output
        assert "score:" in output
        assert "section: body" in output
        assert "chunk:" in output
        assert "pages: p. 1" in output
        assert "snippet:" in output
    finally:
        _close_script_session(session)


def test_retrieval_eval_default_query_file_has_expected_shape() -> None:
    queries = load_eval_queries("scripts/retrieval_eval_queries.json")

    assert len(queries) >= 8
    assert {query.id for query in queries} >= {
        "metric-spaces",
        "complete-metric-spaces",
        "banach-spaces",
        "compactness-metric-spaces",
    }
    assert all(query.query for query in queries)
    assert all(query.expected_keywords for query in queries)


def test_eval_retrieval_runs_queries_and_keyword_summary(tmp_path) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(
                [
                    "Metric spaces use a distance function and neighborhoods.",
                    "Complete metric spaces make every Cauchy sequence converge.",
                    "Banach spaces are complete normed vector spaces.",
                ]
            )
        )
        indexed = index_pdf_file(pdf_path, session=session)
        queries_file = tmp_path / "queries.json"
        queries_file.write_text(
            json.dumps(
                [
                    {
                        "id": "complete",
                        "query": "complete metric spaces",
                        "expected_keywords": ["complete", "Cauchy sequence"],
                    },
                    {
                        "id": "banach",
                        "query": "Banach spaces",
                        "expected_keywords": ["Banach", "normed vector spaces"],
                    },
                ]
            ),
            encoding="utf-8",
        )

        summary = evaluate_retrieval(
            library_item_id=indexed.library_item_id,
            queries_file=queries_file,
            top_k=3,
            session=session,
        )

        assert summary.library_item_id == indexed.library_item_id
        assert [result.query.id for result in summary.results] == ["complete", "banach"]
        assert all(len(result.chunks) == 3 for result in summary.results)
        assert all(result.page_metadata_count == 3 for result in summary.results)
        assert all(result.snippet_source_count == 3 for result in summary.results)
        assert summary.results[0].matched_keywords == ["complete", "Cauchy sequence"]
        assert summary.results[1].matched_keywords == ["Banach", "normed vector spaces"]
    finally:
        _close_script_session(session)


def test_eval_retrieval_cli_prints_baseline_summary(tmp_path, capsys, monkeypatch) -> None:
    session = _create_script_session()
    try:
        pdf_path = tmp_path / "analysis.pdf"
        pdf_path.write_bytes(
            make_pdf_bytes(["A Banach space is a complete normed vector space."])
        )
        indexed = index_pdf_file(pdf_path, session=session)
        queries_file = tmp_path / "queries.json"
        queries_file.write_text(
            json.dumps(
                [
                    {
                        "id": "banach",
                        "query": "Banach spaces",
                        "expected_keywords": ["Banach", "complete"],
                    }
                ]
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr("scripts.eval_retrieval.get_db_session", lambda: session)

        exit_code = eval_retrieval_main(
            [
                "--library-item-id",
                str(indexed.library_item_id),
                "--queries-file",
                str(queries_file),
                "--top-k",
                "1",
                "--max-snippet-chars",
                "40",
            ]
        )

        output = capsys.readouterr().out
        assert exit_code == 0
        assert "Retrieval baseline" in output
        assert "[banach] Banach spaces" in output
        assert "keyword hits: 2/2" in output
        assert "page metadata present: 1/1 chunks" in output
        assert "snippets present: 1/1 chunks" in output
        assert "section: body" in output
        assert "Summary:" in output
    finally:
        _close_script_session(session)
