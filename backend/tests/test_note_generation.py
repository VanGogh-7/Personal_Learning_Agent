import pytest
from pydantic import ValidationError

from app.notes.generation import escape_latex, generate_chat_note_draft
from app.notes.schemas import (
    ChatNoteChunkInput,
    ChatNoteDraftRequest,
    ChatNoteLibraryItemInput,
)


def test_generate_draft_from_global_rag_response() -> None:
    draft = generate_chat_note_draft(
        ChatNoteDraftRequest(
            question="What is a vector space?",
            answer="A vector space is a set with addition and scalar multiplication.",
            retrieved_chunks=[
                ChatNoteChunkInput(
                    id="chunk-1",
                    document_id="doc-1",
                    chunk_index=0,
                    content="A vector space over a field F is closed under addition.",
                    score=0.123,
                )
            ],
            session_id="session-1",
        )
    )

    assert draft.title == "Notes on What is a vector space?"
    assert draft.description == "Generated from Chat response."
    assert draft.library_item_id is None
    assert draft.source_session_id == "session-1"
    assert draft.topic_tags == ["chat-generated"]
    assert r"\subsection{Question}" in draft.content_latex
    assert "A vector space over a field F" in draft.content_latex


def test_generate_draft_from_book_scoped_rag_response() -> None:
    draft = generate_chat_note_draft(
        ChatNoteDraftRequest(
            question="What is compactness?",
            answer="Compactness is a covering property.",
            retrieved_chunks=[],
            library_item=ChatNoteLibraryItemInput(
                id="library-1",
                title="Topology",
                author="James Munkres",
                file_type="md",
                status="indexed",
            ),
        )
    )

    assert draft.library_item_id == "library-1"
    assert r"\subsection{Book Context}" in draft.content_latex
    assert r"\textbf{Title:} Topology" in draft.content_latex
    assert r"\textbf{Author:} James Munkres" in draft.content_latex


def test_generated_draft_escapes_question_and_answer() -> None:
    draft = generate_chat_note_draft(
        ChatNoteDraftRequest(
            question=r"What about A_B & 100% of \sets?",
            answer=r"Use $x_i$ with {braces} and ^ powers.",
            retrieved_chunks=[],
        )
    )

    assert r"A\_B \& 100\%" in draft.content_latex
    assert r"\textbackslash{}sets" in draft.content_latex
    assert r"\$x\_i\$" in draft.content_latex
    assert r"\{braces\}" in draft.content_latex
    assert r"\textasciicircum{} powers" in draft.content_latex


def test_generated_draft_includes_retrieved_chunk_excerpts() -> None:
    draft = generate_chat_note_draft(
        ChatNoteDraftRequest(
            question="What is a group?",
            answer="A group is a set with an operation.",
            retrieved_chunks=[
                ChatNoteChunkInput(chunk_index=3, content="Groups have identity elements."),
                ChatNoteChunkInput(chunk_index=4, content="Groups have inverses."),
            ],
        )
    )

    assert r"\begin{itemize}" in draft.content_latex
    assert "Chunk 1 (index 3): Groups have identity elements." in draft.content_latex
    assert "Chunk 2 (index 4): Groups have inverses." in draft.content_latex


def test_generated_draft_handles_empty_retrieved_chunks() -> None:
    draft = generate_chat_note_draft(
        ChatNoteDraftRequest(
            question="What is an empty source result?",
            answer="No chunks were retrieved.",
            retrieved_chunks=[],
        )
    )

    assert "No retrieved chunks were returned for this response." in draft.content_latex


def test_blank_question_fails() -> None:
    with pytest.raises(ValidationError):
        ChatNoteDraftRequest(question="   ", answer="Answer", retrieved_chunks=[])


def test_blank_answer_fails() -> None:
    with pytest.raises(ValidationError):
        ChatNoteDraftRequest(question="Question", answer="   ", retrieved_chunks=[])


def test_escape_latex_handles_sensitive_characters() -> None:
    assert escape_latex("&%$#_{}~^\\") == (
        r"\&\%\$\#\_\{\}\textasciitilde{}\textasciicircum{}\textbackslash{}"
    )
