from pydantic import BaseModel, field_validator

MIN_TOP_K = 1
MAX_TOP_K = 20


class RagQueryRequest(BaseModel):
    question: str
    top_k: int = 5
    session_id: str | None = None
    include_long_term_memory: bool = False

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value

    @field_validator("top_k")
    @classmethod
    def top_k_must_be_in_range(cls, value: int) -> int:
        if not (MIN_TOP_K <= value <= MAX_TOP_K):
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("session_id must not be empty")
        return value.strip() if value is not None else value


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str | None = None
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: float


class MemoryMetadata(BaseModel):
    used_recent_turns: int
    saved_current_turn: bool
    used_long_term_memories: int = 0


class RagQueryResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    total_retrieved: int
    session_id: str
    memory: MemoryMetadata
