"""Run a lightweight single-book retrieval quality baseline."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.embeddings.providers import get_embedding_provider
from app.rag.retrieval import (
    LibraryItemRagError,
    RetrievedChunkResult,
    retrieve_relevant_chunks_for_library_item,
)

DEFAULT_QUERIES_FILE = Path(__file__).with_name("retrieval_eval_queries.json")


@dataclass(frozen=True)
class RetrievalEvalQuery:
    id: str
    query: str
    expected_keywords: list[str]


@dataclass(frozen=True)
class RetrievalEvalResult:
    query: RetrievalEvalQuery
    chunks: list[RetrievedChunkResult]
    matched_keywords: list[str]

    @property
    def page_metadata_count(self) -> int:
        return sum(
            1
            for chunk in self.chunks
            if chunk.page_start is not None or chunk.page_end is not None
        )

    @property
    def snippet_source_count(self) -> int:
        return sum(1 for chunk in self.chunks if chunk.content.strip())


@dataclass(frozen=True)
class RetrievalEvalSummary:
    library_item_id: uuid.UUID
    results: list[RetrievalEvalResult]


def load_eval_queries(path: str | Path) -> list[RetrievalEvalQuery]:
    """Load a small JSON query set for retrieval baseline checks."""
    query_path = Path(path)
    try:
        raw = json.loads(query_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read queries file: {query_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Queries file is not valid JSON: {query_path}") from exc

    if not isinstance(raw, list):
        raise ValueError("Queries file must contain a JSON list.")

    queries: list[RetrievalEvalQuery] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Query item {index} must be an object.")
        query_id = item.get("id")
        query_text = item.get("query")
        expected_keywords = item.get("expected_keywords")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError(f"Query item {index} must include a non-empty id.")
        if not isinstance(query_text, str) or not query_text.strip():
            raise ValueError(f"Query item {index} must include a non-empty query.")
        if not isinstance(expected_keywords, list) or not all(
            isinstance(keyword, str) and keyword.strip()
            for keyword in expected_keywords
        ):
            raise ValueError(
                f"Query item {index} must include non-empty expected_keywords."
            )
        queries.append(
            RetrievalEvalQuery(
                id=query_id.strip(),
                query=query_text.strip(),
                expected_keywords=[keyword.strip() for keyword in expected_keywords],
            )
        )

    if not queries:
        raise ValueError("Queries file must include at least one query.")
    return queries


def evaluate_retrieval(
    *,
    library_item_id: uuid.UUID | str,
    queries_file: str | Path = DEFAULT_QUERIES_FILE,
    top_k: int = 5,
    include_non_body: bool = False,
    session: Session | None = None,
) -> RetrievalEvalSummary:
    """Run retrieval-only evaluation queries against one Library item."""
    resolved_library_item_id = _parse_uuid(library_item_id, "library_item_id")
    queries = load_eval_queries(queries_file)

    owns_session = session is None
    db = session or get_db_session()
    try:
        provider = get_embedding_provider()
        results: list[RetrievalEvalResult] = []
        for query in queries:
            _, chunks = retrieve_relevant_chunks_for_library_item(
                db,
                resolved_library_item_id,
                query.query,
                top_k=top_k,
                embedding_provider=provider,
                include_non_body=include_non_body,
            )
            results.append(
                RetrievalEvalResult(
                    query=query,
                    chunks=chunks,
                    matched_keywords=_find_keyword_hits(
                        query.expected_keywords,
                        " ".join(chunk.content for chunk in chunks),
                    ),
                )
            )
        return RetrievalEvalSummary(
            library_item_id=resolved_library_item_id,
            results=results,
        )
    finally:
        if owns_session:
            db.close()


def _parse_uuid(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise LibraryItemRagError(f"{field_name} must be a valid UUID.") from exc


def _find_keyword_hits(expected_keywords: list[str], text: str) -> list[str]:
    normalized_text = text.casefold()
    return [
        keyword
        for keyword in expected_keywords
        if keyword.casefold() in normalized_text
    ]


def _format_page(chunk: RetrievedChunkResult) -> str:
    if chunk.page_start is not None and chunk.page_end is not None:
        if chunk.page_start == chunk.page_end:
            return f"p. {chunk.page_start}"
        return f"pp. {chunk.page_start}-{chunk.page_end}"
    if chunk.page_start is not None:
        return f"p. {chunk.page_start}"
    if chunk.page_end is not None:
        return f"p. {chunk.page_end}"
    return "page unknown"


def _make_snippet(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return normalized[: max_chars - 3].rstrip() + "..."


def _format_keyword_hits(result: RetrievalEvalResult) -> str:
    total = len(result.query.expected_keywords)
    hits = len(result.matched_keywords)
    if not result.matched_keywords:
        return f"{hits}/{total} (none)"
    return f"{hits}/{total} ({', '.join(result.matched_keywords)})"


def _print_result(result: RetrievalEvalResult, *, max_snippet_chars: int) -> None:
    print(f"[{result.query.id}] {result.query.query}")
    print(f"keyword hits: {_format_keyword_hits(result)}")
    print(
        "page metadata present: "
        f"{result.page_metadata_count}/{len(result.chunks)} chunks"
    )
    print(f"snippets present: {result.snippet_source_count}/{len(result.chunks)} chunks")
    if not result.chunks:
        print("No chunks returned.")
        print()
        return

    for rank, chunk in enumerate(result.chunks, start=1):
        title = chunk.library_title or chunk.document_title or str(chunk.document_id)
        print(f"{rank}. {title}")
        print(f"   library: {chunk.library_title or 'unknown'}")
        print(f"   document: {chunk.document_title or 'unknown'}")
        print(f"   score: {chunk.score:.6f}")
        print(f"   section: {chunk.section_type}")
        print(f"   chunk: {chunk.chunk_index} ({chunk.chunk_id})")
        print(f"   pages: {_format_page(chunk)}")
        print(f"   snippet: {_make_snippet(chunk.content, max_snippet_chars)}")
    print()


def _print_summary(summary: RetrievalEvalSummary) -> None:
    total_queries = len(summary.results)
    total_expected = sum(
        len(result.query.expected_keywords) for result in summary.results
    )
    total_hits = sum(len(result.matched_keywords) for result in summary.results)
    queries_with_page_metadata = sum(
        1 for result in summary.results if result.page_metadata_count > 0
    )
    queries_with_snippets = sum(
        1 for result in summary.results if result.snippet_source_count > 0
    )

    print("Summary:")
    print(f"queries: {total_queries}")
    print(f"keyword hits: {total_hits}/{total_expected}")
    print(f"queries with page metadata: {queries_with_page_metadata}/{total_queries}")
    print(f"queries with snippets: {queries_with_snippets}/{total_queries}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a lightweight retrieval-only baseline for one Library book."
    )
    parser.add_argument("--library-item-id", required=True, help="Library item UUID to query.")
    parser.add_argument(
        "--queries-file",
        default=str(DEFAULT_QUERIES_FILE),
        help="Path to the retrieval eval query JSON file.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve.")
    parser.add_argument(
        "--include-non-body",
        action="store_true",
        help="Include contents, index, bibliography, and preface chunks.",
    )
    parser.add_argument(
        "--max-snippet-chars",
        type=int,
        default=500,
        help="Maximum characters to print for each retrieved chunk snippet.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.max_snippet_chars < 1:
        print("Evaluation failed: --max-snippet-chars must be positive.", file=sys.stderr)
        return 1

    try:
        summary = evaluate_retrieval(
            library_item_id=args.library_item_id,
            queries_file=args.queries_file,
            top_k=args.top_k,
            include_non_body=args.include_non_body,
        )
    except (LibraryItemRagError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1

    print("Retrieval baseline")
    print(f"Library item: {summary.library_item_id}")
    print(f"Queries: {len(summary.results)}")
    print(f"Top K: {args.top_k}")
    print()
    for result in summary.results:
        _print_result(result, max_snippet_chars=args.max_snippet_chars)
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
