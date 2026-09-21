import uuid

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    conversation_id: uuid.UUID
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    # None picks the server's default model. Validated against the live
    # registry in the router, not here, since availability depends on which
    # provider keys are configured.
    model: str | None = None


class SourceMetadata(BaseModel):
    document_id: str
    filename: str

    # source_path is deliberately absent: it held the absolute path of the
    # file on the server, which should not be disclosed to clients.

    page_number: int | None = None

    section_title: str | None = None
    heading_level: int | None = None

    chunk_index: int

    start_char: int | None = None
    end_char: int | None = None

    language: str | None = None

    tags: list[str] = Field(default_factory=list)


class SourceChunk(BaseModel):
    id: str

    score: float

    retrieval_method: str | None = None

    rerank_score: float | None = None

    text: str

    preview: str | None = None

    metadata: SourceMetadata


class QueryResponse(BaseModel):
    conversation_id: str

    question: str

    answer: str

    # The model id that actually generated the answer, which can differ from
    # the request when none was specified (falls back to the default).
    model: str

    sources: list[SourceChunk] = Field(default_factory=list)

    processing_time_ms: int | None = None

    # The stored id of this answer, so the client can rate it without
    # reloading the conversation. Null if the message could not be found,
    # which the client reads as "rating unavailable" rather than failing.
    message_id: int | None = None


class GenerationModelInfo(BaseModel):
    id: str
    label: str
    provider: str


class GenerationModelsResponse(BaseModel):
    models: list[GenerationModelInfo]
    default: str
