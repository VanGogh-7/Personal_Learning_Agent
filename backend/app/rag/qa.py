from app.rag.retrieval import RetrievedChunkResult

NO_RESULTS_ANSWER = "I could not find relevant information in the current knowledge base."

ANSWER_SNIPPET_LENGTH = 300


def generate_answer(question: str, retrieved_chunks: list[RetrievedChunkResult]) -> str:
    """Build a minimal, deterministic extractive answer from retrieved chunks.

    This is an MVP answer generator, not a full LLM-generated answer: it
    simply surfaces the most relevant retrieved excerpt. It does not call
    any external API.
    """
    if not retrieved_chunks:
        return NO_RESULTS_ANSWER

    top_chunk = retrieved_chunks[0]
    snippet = top_chunk.content.strip()[:ANSWER_SNIPPET_LENGTH]

    source = top_chunk.document_title or str(top_chunk.document_id)

    return (
        "This is a minimal MVP answer (extractive, not LLM-generated), "
        f"based on {len(retrieved_chunks)} retrieved chunk(s). "
        f"Most relevant excerpt from '{source}': \"{snippet}\""
    )
