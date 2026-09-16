"""
The application's implementation of the engine's TraceRecorder protocol.

Thin by design. Keeping it separate from BackgroundTelemetrySink is what
makes the seam explicit: the engine knows only `record_span`/`record_trace`,
the sink knows only queues and rows, and neither imports the other's
concerns. Swapping in an OpenTelemetry exporter later means writing another
class this size, not touching the pipeline.
"""

import logging

from rag.observability.schemas import SpanRecord, TraceRecord

from backend.observability.sink import BackgroundTelemetrySink

logger = logging.getLogger(__name__)


class PersistentTraceRecorder:
    """
    Hands completed records to the background writer.

    Satisfies rag.observability.TraceRecorder structurally rather than by
    inheritance, the same way PersistentConversationStore satisfies
    ConversationStore - the engine never imports this module.
    """

    def __init__(self, sink: BackgroundTelemetrySink) -> None:
        self._sink = sink

    def record_span(self, span: SpanRecord) -> None:
        self._sink.submit(span)

    def record_trace(self, trace: TraceRecord) -> None:
        self._sink.submit(trace)
