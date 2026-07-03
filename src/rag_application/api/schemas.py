from pydantic import BaseModel
from typing import Optional, List, Dict


class QueryRequest(BaseModel):
    conversation_id: str
    question: str
    top_k: int = 5


class SourceChunk(BaseModel):
    id: str
    score: float
    text: str
    metadata: Optional[Dict] = None
    retrieval_method: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: Optional[List[SourceChunk]] = None


class IngestRequest(BaseModel):
    file_path: str


class IngestResponse(BaseModel):
    file_path: str
    status: str
    message: str