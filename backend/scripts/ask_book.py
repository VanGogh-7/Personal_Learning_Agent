"""Ask one indexed book through single-book RAG."""

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
from app.models.document import Document
from app.rag.citations import ChunkCitationResult, build_chunk_citations
from app.rag.qa import generate_answer
from app.rag.retrieval import (
    LibraryItemRagError,
    retrieve_relevant_chunks_for_library_item,
)


@dataclass(frozen=True)
class AskBookSummary:
    answer: str
    library_item_id: uuid.UUID
    citations: list[ChunkCitationResult]


def ask_book(
    question: str,
    *,
    library_item_id: uuid.UUID | str | None = None,
    document_id: uuid.UUID | str | None = None,
    top_k: int = 5,
    session: Session | None = None,
) -> AskBookSummary:
    """Run retrieval and answer generation for one indexed book."""
    if not question.strip():
        raise LibraryItemRagError("Question must not be empty.")

    owns_session = session is None
    db = session or get_db_session()
    try:
        resolved_library_item_id = _resolve_library_item_id(
            db,
            library_item_id=library_item_id,
            document_id=document_id,
        )
        provider = get_embedding_provider()
        context, retrieved_chunks = retrieve_relevant_chunks_for_library_item(
            db,
            resolved_library_item_id,
            question,
            top_k=top_k,
            embedding_provider=provider,
        )
        answer = generate_answer(
            question,
            retrieved_chunks,
            library_item_context=f"Title: {context.title}",
        )
        citations = build_chunk_citations(retrieved_chunks)
        return AskBookSummary(
            answer=answer,
            library_item_id=resolved_library_item_id,
            citations=citations,
        )
    finally:
        if owns_session:
            db.close()


def _resolve_library_item_id(
    session: Session,
    *,
    library_item_id: uuid.UUID | str | None,
    document_id: uuid.UUID | str | None,
) -> uuid.UUID:
    if library_item_id is not None:
        return _parse_uuid(library_item_id, "library_item_id")

    if document_id is None:
        raise LibraryItemRagError("Either --library-item-id or --document-id is required.")

    parsed_document_id = _parse_uuid(document_id, "document_id")
    document = session.get(Document, parsed_document_id)
    if document is None:
        raise LibraryItemRagError("Document not found.")
    if document.library_item_id is None:
        raise LibraryItemRagError("Document is not linked to a Library item.")
    return document.library_item_id


def _parse_uuid(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise LibraryItemRagError(f"{field_name} must be a valid UUID.") from exc


def _format_page(citation: ChunkCitationResult) -> str:
    if citation.page_number is not None:
        return f"p. {citation.page_number}"
    if citation.page_start is not None and citation.page_end is not None:
        return f"pp. {citation.page_start}-{citation.page_end}"
    if citation.page_start is not None:
        return f"p. {citation.page_start}"
    return "page unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask a question against one indexed Library PDF/book."
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--library-item-id", help="Library item UUID to query.")
    scope.add_argument("--document-id", help="Document UUID to query.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve.")
    parser.add_argument("question", nargs="+", help="Question to ask.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    question = " ".join(args.question)

    try:
        summary = ask_book(
            question,
            library_item_id=args.library_item_id,
            document_id=args.document_id,
            top_k=args.top_k,
        )
    except (LibraryItemRagError, ValueError) as exc:
        print(f"Question failed: {exc}", file=sys.stderr)
        return 1

    print("Answer:")
    print(summary.answer)
    print()
    print("Citations:")
    if not summary.citations:
        print("No citations returned.")
    for citation in summary.citations:
        title = citation.library_title or citation.document_title or citation.document_id
        print(
            f"- {citation.citation_id}: {title}, chunk {citation.chunk_index}, "
            f"{_format_page(citation)}"
        )
        print(f"  Excerpt: {citation.excerpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
