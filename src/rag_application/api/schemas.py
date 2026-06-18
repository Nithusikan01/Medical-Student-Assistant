from pydantic import BaseModel
from typing import Optional, List

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5

class QueryResponse(BaseModel):
    question: str
    answer: str
    source_documents: Optional[List[str]] = None