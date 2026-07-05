from pydantic import BaseModel


class Chunk(BaseModel):
    index: int
    content: str
    char_start: int
    char_end: int


class ChunkTextRequest(BaseModel):
    text: str
    chunk_size: int = 800
    chunk_overlap: int = 100


class ChunkTextResponse(BaseModel):
    chunks: list[Chunk]
    total_chunks: int


class LoadFileRequest(BaseModel):
    file_path: str
    chunk_size: int = 800
    chunk_overlap: int = 100


class LoadFileResponse(BaseModel):
    file_path: str
    chunks: list[Chunk]
    total_chunks: int
