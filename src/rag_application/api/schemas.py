from pydantic import BaseModel
from typing import Optional, List

class QueryRequest(BaseModel):
    conversation_id: str
    question: str
    

class QueryResponse(BaseModel):
    question: str
    answer: str
    source_documents: Optional[List[str]] = None


class IngestRequest(BaseModel):
    file_path: str


class IngestResponse(BaseModel):
    file_path: str
    status: str
    message: str
