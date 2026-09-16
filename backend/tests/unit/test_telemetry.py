"""
The application side of telemetry: config, the background writer, and the
end-to-end path from a tracer span to a database row.

The regression tests at the bottom are the ones that matter most - they
encode the rule that an unavailable telemetry database leaves the traced
code working.
"""

import queue

import pytest
import sqlalchemy as sa
from rag.observability import Stage, Tracer
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import RagSpan, RagTrace
from backend.observability.config import TelemetryConfig, load_telemetry_config
from backend.observability.recorder import PersistentTraceRecorder
from backend.observability.sink import BackgroundTelemetrySink


@pytest.fixture
def config() -> TelemetryConfig:
    return TelemetryConfig(
        queue_size=100,
        batch_size=10,
        flush_interval_seconds=0.05,
        shutdown_timeout_seconds=2.0,
    )


@pytest.fixture
def sink(
    session_factory: sessionmaker[Session],
    config: TelemetryConfig,
) -> BackgroundTelemetrySink:
    return BackgroundTelemetrySink(session_factory, config)


@pytest.fixture
def tracer(sink: BackgroundTelemetrySink) -> Tracer:
    return Tracer(
        PersistentTraceRecorder(sink),
        environment="test",
        app_version="0.0.0-test",
    )


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


def test_config_defaults_to_enabled_and_privacy_preserving(monkeypatch):
    for name in (
        "TELEMETRY_ENABLED",
        "TELEMETRY_SAMPLE_RATE",
        "TELEMETRY_CAPTURE_TEXT",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_telemetry_config()

    assert config.enabled is True
    assert config.sample_rate == 1.0

    # Raw query and answer text stays out of telemetry unless asked for.
    assert config.capture_text is False


def test_sample_rate_is_clamped(monkeypatch):
    monkeypatch.setenv("TELEMETRY_SAMPLE_RATE", "7.5")
    assert load_telemetry_config().sample_rate == 1.0

    monkeypatch.setenv("TELEMETRY_SAMPLE_RATE", "-1")
    assert load_telemetry_config().sample_rate == 0.0


def test_unparseable_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("TELEMETRY_QUEUE_SIZE", "not-a-number")

    assert load_telemetry_config().queue_size == 2000


# ----------------------------------------------------------------------
# The writer
# ----------------------------------------------------------------------


def test_spans_and_traces_are_written(tracer, sink, db: Session):
    with tracer.trace(request_id="req-1") as trace:
        trace_id = trace.trace_id

        with tracer.span(Stage.RETRIEVAL) as span:
            span.set(result_count=20)

    sink.flush_now()

    stored_trace = db.get(RagTrace, trace_id)

    assert stored_trace is not None
    assert stored_trace.request_id == "req-1"
    assert stored_trace.status == "ok"
    assert stored_trace.environment == "test"
    assert stored_trace.duration_ms >= 0.0

    stored_span = db.scalars(
        sa.select(RagSpan).where(RagSpan.trace_id == trace_id)
    ).one()

    assert stored_span.stage == "retrieval"
    assert stored_span.meta == {"result_count": 20}


def test_conversation_and_user_ids_are_stored_for_joining(tracer, sink, db, user):
    import uuid

    conversation_id = uuid.uuid4()

    with tracer.trace(
        conversation_id=str(conversation_id),
        user_id=str(user.id),
    ) as trace:
        trace_id = trace.trace_id

    sink.flush_now()

    stored = db.get(RagTrace, trace_id)

    assert stored.conversation_id == conversation_id
    assert stored.user_id == user.id


def test_a_malformed_id_costs_the_column_not_the_row(tracer, sink, db):
    with tracer.trace(conversation_id="not-a-uuid") as trace:
        trace_id = trace.trace_id

    sink.flush_now()

    stored = db.get(RagTrace, trace_id)

    assert stored is not None
    assert stored.conversation_id is None


def test_errors_are_stored_with_their_type(tracer, sink, db):
    with pytest.raises(ValueError), tracer.trace() as trace:
        trace_id = trace.trace_id

        with tracer.span(Stage.GENERATION):
            raise ValueError("nope")

    sink.flush_now()

    stored_span = db.scalars(
        sa.select(RagSpan).where(RagSpan.trace_id == trace_id)
    ).one()

    assert stored_span.status == "error"
    assert stored_span.error_type == "ValueError"


def test_spans_may_be_written_before_their_trace(sink, db, tracer):
    """
    Spans close first, so the child row legitimately precedes the parent.
    A foreign key here would reject it; this test pins that it does not.
    """

    with tracer.trace() as trace:
        trace_id = trace.trace_id

        with tracer.span(Stage.QUERY_REWRITE):
            pass

        # Flush while the trace is still open: only the span exists yet.
        sink.flush_now()

    assert db.get(RagTrace, trace_id) is None
    assert db.scalars(sa.select(RagSpan).where(RagSpan.trace_id == trace_id)).all()

    sink.flush_now()

    assert db.get(RagTrace, trace_id) is not None


def test_the_worker_thread_writes_and_stops_cleanly(tracer, sink, db):
    sink.start()

    try:
        with tracer.trace() as trace:
            trace_id = trace.trace_id

            with tracer.span(Stage.FUSION):
                pass
    finally:
        # stop() drains what is queued before joining the thread.
        sink.stop()

    assert db.get(RagTrace, trace_id) is not None
    assert sink.written == 2


# ----------------------------------------------------------------------
# Regressions: telemetry failure must not become RAG failure
# ----------------------------------------------------------------------


def test_an_unavailable_database_does_not_raise(config):
    def broken_session_factory():
        raise RuntimeError("database is gone")

    sink = BackgroundTelemetrySink(broken_session_factory, config)
    tracer = Tracer(PersistentTraceRecorder(sink))

    result = None

    with tracer.trace(), tracer.span(Stage.GENERATION):
        result = "the answer"

    sink.flush_now()

    assert result == "the answer"
    assert sink.dropped > 0
    assert sink.written == 0


def test_a_full_queue_drops_records_instead_of_blocking(session_factory):
    sink = BackgroundTelemetrySink(
        session_factory,
        TelemetryConfig(queue_size=1, batch_size=10),
    )

    tracer = Tracer(PersistentTraceRecorder(sink))

    # No worker is running, so nothing is consuming the queue.
    with tracer.trace():
        for _ in range(20):
            with tracer.span(Stage.DENSE_RETRIEVAL):
                pass

    assert sink.dropped > 0


def test_submit_never_raises_on_a_broken_queue(sink, monkeypatch):
    def explode(_record):
        raise queue.Full()

    monkeypatch.setattr(sink._queue, "put_nowait", explode)

    sink.submit(object())

    assert sink.dropped == 1


def test_stopping_a_sink_that_never_started_is_harmless(sink):
    sink.stop()
