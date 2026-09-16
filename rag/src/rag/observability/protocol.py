"""
The storage seam for telemetry.

Same pattern as ConversationStore and ChunkSink: the engine depends on a
Protocol it defines, and the application supplies the implementation that
knows about databases. Nothing in `rag` imports a recorder implementation,
so the engine stays usable - and fully testable - with no telemetry backend
at all.

An implementation must never raise and never block for long: Tracer guards
every call anyway (a monitoring failure must not become a RAG failure), but
an implementation that raises on every span turns that guard into a hot
exception path. Queue the record and return.
"""

from typing import Protocol

from rag.observability.schemas import SpanRecord, TraceRecord


class TraceRecorder(Protocol):
    """Receives completed telemetry records."""

    def record_span(self, span: SpanRecord) -> None: ...

    def record_trace(self, trace: TraceRecord) -> None: ...
