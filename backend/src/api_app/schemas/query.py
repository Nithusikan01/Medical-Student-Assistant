import uuid
from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    conversation_id: uuid.UUID
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceMetadata(BaseModel):
    document_id: str
    filename: str

    # source_path is deliberately absent: it held the absolute path of the
    # file on the server, which should not be disclosed to clients.

    page_number: Optional[int] = None

    section_title: Optional[str] = None
    heading_level: Optional[int] = None

    chunk_index: int

    start_char: Optional[int] = None
    end_char: Optional[int] = None

    language: Optional[str] = None

    tags: list[str] = Field(default_factory=list)


class SourceChunk(BaseModel):
    id: str

    score: float

    retrieval_method: Optional[str] = None

    rerank_score: Optional[float] = None

    text: str

    preview: Optional[str] = None

    metadata: SourceMetadata


class QueryResponse(BaseModel):
    conversation_id: str

    question: str

    answer: str

    sources: list[SourceChunk] = Field(default_factory=list)

    processing_time_ms: Optional[int] = None
