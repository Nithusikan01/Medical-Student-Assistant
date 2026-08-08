from typing import Optional

from pydantic import BaseModel


class IngestResponse(BaseModel):
    filename: str
    status: str
    message: str


class QueryRequest(BaseModel):
    conversation_id: str
    question: str
    top_k: int = 5


class SourceMetadata(BaseModel):
    document_id: str
    filename: str
    source_path: str

    page_number: Optional[int] = None

    section_title: Optional[str] = None
    heading_level: Optional[int] = None

    chunk_index: int

    start_char: Optional[int] = None
    end_char: Optional[int] = None

    language: Optional[str] = None

    tags: list[str] = []


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

    sources: list[SourceChunk] = []

    processing_time_ms: Optional[int] = None