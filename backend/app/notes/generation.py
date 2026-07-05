from app.notes.schemas import ChatNoteDraftRequest, ChatNoteDraftResponse

MAX_TITLE_QUESTION_CHARS = 80
MAX_CHUNK_EXCERPT_CHARS = 240

LATEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def generate_chat_note_draft(request: ChatNoteDraftRequest) -> ChatNoteDraftResponse:
    """Build a deterministic LaTeX note draft from a Chat/RAG response."""

    title = _build_title(request.question)
    content = _build_latex_content(request, title)
    library_item_id = request.library_item.id if request.library_item else None

    return ChatNoteDraftResponse(
        title=title,
        content_latex=content,
        description="Generated from Chat response.",
        library_item_id=library_item_id,
        source_session_id=request.session_id,
        topic_tags=["chat-generated"],
    )


def escape_latex(value: str) -> str:
    return "".join(LATEX_ESCAPE_MAP.get(char, char) for char in value)


def _build_title(question: str) -> str:
    compact_question = " ".join(question.strip().split())
    if len(compact_question) > MAX_TITLE_QUESTION_CHARS:
        compact_question = f"{compact_question[:MAX_TITLE_QUESTION_CHARS].rstrip()}..."
    return f"Notes on {compact_question}"


def _build_latex_content(request: ChatNoteDraftRequest, title: str) -> str:
    sections = [
        rf"\section{{{escape_latex(title)}}}",
        "",
    ]

    if request.library_item is not None:
        sections.extend(
            [
                r"\subsection{Book Context}",
                "",
                rf"\textbf{{Title:}} {escape_latex(request.library_item.title)}",
                "",
            ]
        )
        if request.library_item.author:
            sections.extend(
                [rf"\textbf{{Author:}} {escape_latex(request.library_item.author)}", ""]
            )
        if request.library_item.file_type:
            sections.extend(
                [rf"\textbf{{File type:}} {escape_latex(request.library_item.file_type)}", ""]
            )

    sections.extend(
        [
            r"\subsection{Question}",
            "",
            escape_latex(request.question),
            "",
            r"\subsection{Answer}",
            "",
            escape_latex(request.answer),
            "",
            r"\subsection{Sources}",
            "",
        ]
    )

    if request.retrieved_chunks:
        sections.append(r"\begin{itemize}")
        for index, chunk in enumerate(request.retrieved_chunks, start=1):
            excerpt = _truncate_excerpt(chunk.content)
            source_label = _build_chunk_label(index, chunk.chunk_index)
            sections.append(rf"  \item {source_label}: {escape_latex(excerpt)}")
        sections.append(r"\end{itemize}")
    else:
        sections.append("No retrieved chunks were returned for this response.")

    sections.extend(
        [
            "",
            r"\subsection{Remarks}",
            "",
            r"% Add your own notes here.",
            "",
        ]
    )
    return "\n".join(sections)


def _truncate_excerpt(content: str) -> str:
    compact_content = " ".join(content.strip().split())
    if len(compact_content) <= MAX_CHUNK_EXCERPT_CHARS:
        return compact_content
    return f"{compact_content[:MAX_CHUNK_EXCERPT_CHARS].rstrip()}..."


def _build_chunk_label(source_number: int, chunk_index: int | None) -> str:
    if chunk_index is None:
        return f"Chunk {source_number}"
    return f"Chunk {source_number} (index {chunk_index})"
