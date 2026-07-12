from app.memory.long_term import LongTermMemoryResult
from app.memory.short_term import ConversationTurnResult
from app.llm.output_protocol import MARKDOWN_MATH_OUTPUT_INSTRUCTIONS
from app.llm.providers import (
    DETERMINISTIC_ANSWER_MARKER,
    DeterministicLLMProvider,
    LLMProvider,
    get_llm_provider,
)
from app.rag.citations import build_chunk_citations, format_citation_source
from app.rag.retrieval import RetrievedChunkResult

NO_RESULTS_ANSWER = (
    "I could not find relevant information in the current knowledge base."
)

ANSWER_SNIPPET_LENGTH = 300

# Bounded: only the single most recent prior question is ever mentioned,
# and it is truncated defensively before being included in the answer.
RECENT_QUESTION_SNIPPET_LENGTH = 200

# Bounded: only the single most relevant long-term memory is ever
# mentioned, and it is truncated defensively before being included.
LONG_TERM_MEMORY_SNIPPET_LENGTH = 200


def generate_answer(
    question: str,
    retrieved_chunks: list[RetrievedChunkResult],
    recent_turns: list[ConversationTurnResult] | None = None,
    long_term_memories: list[LongTermMemoryResult] | None = None,
    library_item_context: str | None = None,
    llm_provider: LLMProvider | None = None,
) -> str:
    """Build a RAG answer through the configured LLM provider boundary.

    The default provider is deterministic and preserves the original MVP
    extractive answer text. Real providers are selected only through
    explicit configuration.
    """
    provider = llm_provider or get_llm_provider()
    deterministic_answer = build_deterministic_answer(
        question,
        retrieved_chunks,
        recent_turns=recent_turns,
        long_term_memories=long_term_memories,
    )
    prompt = build_rag_prompt(
        question,
        retrieved_chunks,
        recent_turns=recent_turns,
        long_term_memories=long_term_memories,
        library_item_context=library_item_context,
        deterministic_answer=deterministic_answer
        if isinstance(provider, DeterministicLLMProvider)
        else None,
    )
    return provider.generate(prompt)


def build_deterministic_answer(
    question: str,
    retrieved_chunks: list[RetrievedChunkResult],
    recent_turns: list[ConversationTurnResult] | None = None,
    long_term_memories: list[LongTermMemoryResult] | None = None,
) -> str:
    """Build the deterministic extractive answer used by default."""
    if not retrieved_chunks:
        answer = NO_RESULTS_ANSWER
    else:
        top_chunk = retrieved_chunks[0]
        snippet = top_chunk.content.strip()[:ANSWER_SNIPPET_LENGTH]
        source = top_chunk.document_title or str(top_chunk.document_id)

        answer = (
            "This is a minimal MVP answer (extractive, not LLM-generated), "
            f"based on {len(retrieved_chunks)} retrieved chunk(s). "
            f"Most relevant excerpt from '{source}': \"{snippet}\""
        )

    if recent_turns:
        previous_question = recent_turns[-1].question.strip()[
            :RECENT_QUESTION_SNIPPET_LENGTH
        ]
        answer += (
            " I considered your recent session context, including your "
            f'previous question: "{previous_question}".'
        )

    if long_term_memories:
        top_memory = long_term_memories[0]
        memory_snippet = top_memory.content.strip()[:LONG_TERM_MEMORY_SNIPPET_LENGTH]
        answer += (
            f" I also found a relevant long-term memory ({top_memory.memory_type}): "
            f'"{memory_snippet}".'
        )

    return answer


def build_rag_prompt(
    question: str,
    retrieved_chunks: list[RetrievedChunkResult],
    recent_turns: list[ConversationTurnResult] | None = None,
    long_term_memories: list[LongTermMemoryResult] | None = None,
    library_item_context: str | None = None,
    deterministic_answer: str | None = None,
) -> str:
    """Build a small prompt for RAG answer generation.

    This is intentionally plain text, not a prompt framework. The final
    deterministic reference section lets the default provider preserve
    exact historical behavior without reaching external services.
    """

    lines = [
        "Answer the learning question from the retrieved local-library context.",
        "Use only the retrieved sources for claims about what the book says.",
        "Cite each book-supported claim with the matching source ID, such as [S1].",
        "Use only the shown [S#] IDs; do not use alternate numeric labels or invent IDs.",
        "If the retrieved context is weak, indirect, or insufficient, say so clearly.",
        "You may add explanatory rephrasing, but distinguish it from what the book explicitly supports.",
        *MARKDOWN_MATH_OUTPUT_INSTRUCTIONS,
        "",
        "Return this structure:",
        "Answer",
        "<answer with [S#] citations>",
        "Do not write a Sources section; structured source metadata is rendered separately.",
        "",
        "Question:",
        question.strip(),
    ]

    if library_item_context and library_item_context.strip():
        lines.extend(["", "Book context:", library_item_context.strip()])

    if retrieved_chunks:
        lines.extend(["", "Retrieved local sources:"])
        for citation in build_chunk_citations(retrieved_chunks):
            lines.append(f"[{citation.citation_id}]")
            lines.append(format_citation_source(citation))
            lines.append("Text:")
            lines.append(citation.content.strip())
    else:
        lines.extend(
            ["", "Retrieved local sources:", "No relevant sources were retrieved."]
        )

    if recent_turns:
        lines.extend(["", "Recent session context:"])
        for turn in recent_turns:
            lines.append(f"- Previous question: {turn.question.strip()}")

    if long_term_memories:
        lines.extend(["", "Relevant long-term memories:"])
        for memory in long_term_memories:
            lines.append(f"- {memory.memory_type}: {memory.content.strip()}")

    if deterministic_answer is not None:
        lines.extend(["", DETERMINISTIC_ANSWER_MARKER, deterministic_answer])

    return "\n".join(lines)
