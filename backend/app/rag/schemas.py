from pydantic import BaseModel, field_validator

MIN_TOP_K = 1
MAX_TOP_K = 20


class RagQueryRequest(BaseModel):
    question: str
    top_k: int = 5

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


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str | None = None
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: float


class RagQueryResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    total_retrieved: int
