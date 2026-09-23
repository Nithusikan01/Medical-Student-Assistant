"""
Typed telemetry records.

These are plain dataclasses on purpose: the engine ships no pydantic and no
ORM, and a recorder implementation is free to persist them however it likes
(see rag/observability/protocol.py). Structured records rather than log
strings is what makes the data queryable later - section 38 of the
observability spec.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Stage(str, Enum):
    """
    The pipeline stages this application actually has.

    Deliberately not a superset of every stage a RAG system could have: a
    span is only ever created for work that really runs, so an empty stage
    in a trace means "did not happen", never "not instrumented".
    """

    # Query path
    MEMORY_LOAD = "memory_load"
    SMALL_TALK = "small_talk"
    QUERY_REWRITE = "query_rewrite"
    CACHE_LOOKUP = "cache_lookup"
    RETRIEVAL = "retrieval"
    QUERY_EMBEDDING = "query_embedding"
    DENSE_RETRIEVAL = "dense_retrieval"
    BM25_RETRIEVAL = "bm25_retrieval"
    FUSION = "fusion"
    RERANKING = "reranking"
    CONTEXT_BUILD = "context_build"
    GENERATION = "generation"
    MEMORY_WRITE = "memory_write"
    SUMMARIZATION = "summarization"

    # Ingestion path
    INGESTION = "ingestion"
    DOCUMENT_LOAD = "document_load"
    INGESTION_BATCH = "ingestion_batch"
    DOCUMENT_EMBEDDING = "document_embedding"
    VECTOR_UPSERT = "vector_upsert"


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SpanRecord:
    """
    One completed unit of work inside a trace.

    `metadata` carries stage-specific numbers (counts, scores, model names,
    configuration) and is expected to have been sanitised already - see
    rag/observability/sanitize.py. Payloads (prompts, answers, chunk text)
    do not belong here; section 55 of the spec, and storing them would turn
    the telemetry tables into a second copy of the corpus.
    """

    trace_id: str
    span_id: str
    stage: str

    started_at: datetime
    ended_at: datetime
    duration_ms: float

    status: SpanStatus = SpanStatus.OK

    # Position within the trace, 1-based. The ordering key for a waterfall:
    # started_at ties, because the clock is coarser than the gap between a
    # parent span and the child it opens, so retrieval, dense_retrieval and
    # query_embedding routinely share one timestamp to the microsecond.
    sequence: int = 0

    parent_span_id: str | None = None
    error_type: str | None = None

    # What kind of failure this was - rate limit, timeout, upstream, auth,
    # validation, internal. The type name says which exception class was
    # raised; this says what an operator should do about it.
    error_category: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """
    One end-to-end request, the root that spans hang off.

    Written when the trace closes, which is *after* its spans - so a store
    must not require the trace row to exist before accepting a span.
    """

    trace_id: str

    started_at: datetime
    ended_at: datetime
    duration_ms: float

    status: SpanStatus = SpanStatus.OK

    request_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None

    error_type: str | None = None
    error_category: str | None = None

    environment: str | None = None
    app_version: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
