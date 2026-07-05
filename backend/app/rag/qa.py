from app.memory.short_term import ConversationTurnResult
from app.rag.retrieval import RetrievedChunkResult

NO_RESULTS_ANSWER = "I could not find relevant information in the current knowledge base."

ANSWER_SNIPPET_LENGTH = 300

# Bounded: only the single most recent prior question is ever mentioned,
# and it is truncated defensively before being included in the answer.
RECENT_QUESTION_SNIPPET_LENGTH = 200


def generate_answer(
    question: str,
    retrieved_chunks: list[RetrievedChunkResult],
    recent_turns: list[ConversationTurnResult] | None = None,
) -> str:
    """Build a minimal, deterministic extractive answer from retrieved chunks.

    This is an MVP answer generator, not a full LLM-generated answer: it
    simply surfaces the most relevant retrieved excerpt. It does not call
    any external API. `recent_turns` is the bounded list of recent
    short-term-memory turns for the session (see
    app.memory.short_term.get_recent_turns), oldest first; when non-empty,
    the answer deterministically mentions only the single most recent
    prior question (truncated), never the full conversation history.
    """
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
        previous_question = recent_turns[-1].question.strip()[:RECENT_QUESTION_SNIPPET_LENGTH]
        answer += (
            " I considered your recent session context, including your "
            f'previous question: "{previous_question}".'
        )

    return answer
