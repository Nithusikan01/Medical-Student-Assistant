import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    error: str | None = None
    page_count: int | None = None
    chunk_count: int = 0
    size_bytes: int | None = None
    uploaded_by_email: str | None = None
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        document,
        uploaded_by_email: str | None = None,
    ) -> "DocumentResponse":
        return cls(
            id=document.id,
            filename=document.filename,
            status=document.status,
            error=document.error,
            page_count=document.page_count,
            chunk_count=document.chunk_count,
            size_bytes=document.size_bytes,
            uploaded_by_email=uploaded_by_email,
            created_at=document.created_at,
        )


class IngestResponse(BaseModel):
    filename: str
    status: str
    message: str
    document: DocumentResponse | None = None
