from app.memory.long_term import LongTermMemoryResult
from app.memory.short_term import ConversationTurnResult
from app.rag.retrieval import RetrievedChunkResult

NO_RESULTS_ANSWER = "I could not find relevant information in the current knowledge base."

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
) -> str:
    """Build a minimal, deterministic extractive answer from retrieved chunks.

    This is an MVP answer generator, not a full LLM-generated answer: it
    simply surfaces the most relevant retrieved excerpt. It does not call
    any external API. `recent_turns` is the bounded list of recent
    short-term-memory turns for the session (see
    app.memory.short_term.get_recent_turns), oldest first; when non-empty,
    the answer deterministically mentions only the single most recent
    prior question (truncated), never the full conversation history.
    `long_term_memories` is the bounded list of relevant long-term
    memories (see app.memory.long_term.search_memories); when non-empty,
    the answer deterministically mentions only the single most relevant
    memory (truncated), never the full memory list.
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

    if long_term_memories:
        top_memory = long_term_memories[0]
        memory_snippet = top_memory.content.strip()[:LONG_TERM_MEMORY_SNIPPET_LENGTH]
        answer += (
            f' I also found a relevant long-term memory ({top_memory.memory_type}): '
            f'"{memory_snippet}".'
        )

    return answer
