"""Search one indexed book and print retrieved chunks without LLM generation."""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class SearchBookSummary:
    library_item_id: uuid.UUID
    query: str
    chunks: list[RetrievedChunkResult]


def search_book(
    query: str,
    *,
    library_item_id: uuid.UUID | str,
    top_k: int = 5,
    include_non_body: bool = False,
    session: Session | None = None,
) -> SearchBookSummary:
    """Run single-book retrieval without answer generation."""
    if not query.strip():
        raise LibraryItemRagError("Query must not be empty.")

    resolved_library_item_id = _parse_uuid(library_item_id, "library_item_id")
    owns_session = session is None
    db = session or get_db_session()
    try:
        provider = get_embedding_provider()
        _, chunks = retrieve_relevant_chunks_for_library_item(
            db,
            resolved_library_item_id,
            query,
            top_k=top_k,
            embedding_provider=provider,
            include_non_body=include_non_body,
        )
        return SearchBookSummary(
            library_item_id=resolved_library_item_id,
            query=query,
            chunks=chunks,
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search one indexed Library PDF/book without LLM generation."
    )
    parser.add_argument("--library-item-id", required=True, help="Library item UUID to query.")
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
    parser.add_argument("query", nargs="+", help="Search query.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    query = " ".join(args.query)

    if args.max_snippet_chars < 1:
        print("Search failed: --max-snippet-chars must be positive.", file=sys.stderr)
        return 1

    try:
        summary = search_book(
            query,
            library_item_id=args.library_item_id,
            top_k=args.top_k,
            include_non_body=args.include_non_body,
        )
    except (LibraryItemRagError, ValueError) as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        return 1

    print(f"Query: {summary.query}")
    print(f"Library item: {summary.library_item_id}")
    print()
    print("Retrieved chunks:")
    if not summary.chunks:
        print("No chunks returned.")
    for rank, chunk in enumerate(summary.chunks, start=1):
        title = chunk.library_title or chunk.document_title or str(chunk.document_id)
        print(f"{rank}. {title}")
        print(f"   library: {chunk.library_title or 'unknown'}")
        print(f"   document: {chunk.document_title or 'unknown'}")
        print(f"   score: {chunk.score:.6f}")
        print(f"   section: {chunk.section_type}")
        print(f"   chunk: {chunk.chunk_index} ({chunk.chunk_id})")
        print(f"   pages: {_format_page(chunk)}")
        print(f"   snippet: {_make_snippet(chunk.content, args.max_snippet_chars)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
