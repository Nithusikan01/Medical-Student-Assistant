"""
Gathering the numbers and telling someone.

The rules themselves are tested in test_alerts.py; this covers the parts
that touch the outside world - what the snapshot reports when there is
nothing to measure, and that a failing delivery cannot take the
evaluator down with it.
"""

import uuid
from datetime import UTC, datetime, timedelta

from backend.db.models import Document, RagSpan, RagTrace
from backend.observability.aggregation import TimeWindow
from backend.observability.alerts import AlertSettings
from backend.services.alerting import (
    AlertService,
    FanOutSink,
    LoggingAlertSink,
    gather_snapshot,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

WINDOW = TimeWindow(start=NOW - timedelta(minutes=15), end=NOW)


def add_trace(db, *, status="ok", status_code=200, duration_ms=100.0, minutes_ago=5.0):
    started = NOW - timedelta(minutes=minutes_ago)

    db.add(
        RagTrace(
            id=uuid.uuid4().hex,
            status=status,
            status_code=status_code,
            route="/api/query",
            started_at=started,
            ended_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
        )
    )
    db.commit()


def add_bm25_span(db, *, results: int, minutes_ago=5.0):
    started = NOW - timedelta(minutes=minutes_ago)

    db.add(
        RagSpan(
            id=uuid.uuid4().hex,
            trace_id=uuid.uuid4().hex,
            stage="bm25_retrieval",
            sequence=1,
            status="ok",
            started_at=started,
            ended_at=started + timedelta(milliseconds=5),
            duration_ms=5.0,
            meta={"result_count": results},
        )
    )
    db.commit()


class RecordingSink:
    def __init__(self) -> None:
        self.delivered = []

    def deliver(self, alerts) -> None:
        self.delivered.extend(alerts)


class BrokenSink:
    def deliver(self, alerts) -> None:
        raise RuntimeError("the webhook is on fire")


# ----------------------------------------------------------------------
# The snapshot
# ----------------------------------------------------------------------


def test_an_empty_window_has_no_error_rate(db, session_factory):
    """
    Not zero. An outage that stopped all traffic would otherwise read as
    perfect health.
    """

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW)

    assert snapshot["requests"] == 0.0
    assert snapshot["error_rate"] is None
    assert snapshot["p95_ms"] is None


def test_failures_are_counted(db, session_factory):
    for _ in range(3):
        add_trace(db, status="ok")

    add_trace(db, status="error", status_code=500)

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW)

    assert snapshot["requests"] == 4.0
    assert snapshot["error_rate"] == 0.25


def test_unpriced_spend_is_not_reported_as_free(db, session_factory):
    """
    Null, not zero. "No pricing row configured" must never chart as
    "costs nothing".
    """

    add_trace(db)

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW)

    assert snapshot["cost_per_hour_usd"] is None


def test_lexical_silence_is_measured(db, session_factory):
    for _ in range(3):
        add_bm25_span(db, results=0)

    add_bm25_span(db, results=5)

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW)

    assert snapshot["bm25_calls"] == 4.0
    assert snapshot["bm25_empty_rate"] == 0.75


def test_a_stuck_ingestion_reaches_the_snapshot(db, session_factory):
    db.add(
        Document(
            id=uuid.uuid4(),
            filename="book.pdf",
            status="processing",
            created_at=datetime.now(UTC) - timedelta(days=2),
            updated_at=datetime.now(UTC) - timedelta(days=2),
        )
    )
    db.commit()

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW)

    assert snapshot["stalled_documents"] == 1.0


def test_dropped_telemetry_is_carried_through(db, session_factory):
    """
    So "monitoring is lossy right now" can itself be an alert, rather
    than something noticed later when the numbers look wrong.
    """

    with session_factory() as session:
        snapshot = gather_snapshot(session, window=WINDOW, dropped_records=12)

    assert snapshot["dropped_records"] == 12.0


# ----------------------------------------------------------------------
# The service
# ----------------------------------------------------------------------


def service(session_factory, sink, **overrides) -> AlertService:
    return AlertService(
        session_factory,
        settings=AlertSettings(min_requests=1).with_overrides(**overrides),
        sink=sink,
    )


def test_a_breach_is_delivered(db, session_factory):
    add_trace(db, status="error", status_code=500, minutes_ago=1)

    sink = RecordingSink()

    service(session_factory, sink).evaluate_once(now=NOW)

    assert [alert.key for alert in sink.delivered] == ["error_rate"]


def test_a_continuing_breach_is_not_delivered_twice(db, session_factory):
    add_trace(db, status="error", status_code=500, minutes_ago=1)

    sink = RecordingSink()
    evaluator = service(session_factory, sink)

    evaluator.evaluate_once(now=NOW)
    evaluator.evaluate_once(now=NOW + timedelta(minutes=5))

    assert len(sink.delivered) == 1


def test_a_healthy_pass_delivers_nothing(db, session_factory):
    add_trace(db)

    sink = RecordingSink()

    service(session_factory, sink).evaluate_once(now=NOW)

    assert sink.delivered == []


def test_the_latest_verdict_is_readable(db, session_factory):
    add_trace(db)

    evaluator = service(session_factory, RecordingSink())
    evaluator.evaluate_once(now=NOW)

    alerts, evaluated_at = evaluator.current()

    assert evaluated_at == NOW
    assert alerts


def test_nothing_evaluated_yet_reports_no_time(session_factory):
    alerts, evaluated_at = service(session_factory, RecordingSink()).current()

    assert alerts == []
    assert evaluated_at is None


# ----------------------------------------------------------------------
# Failure containment
# ----------------------------------------------------------------------


def test_a_failing_sink_does_not_stop_the_others():
    """
    An alerting system that takes the application down with it has
    inverted its own purpose.
    """

    recording = RecordingSink()

    FanOutSink([BrokenSink(), recording]).deliver([_an_alert()])

    assert len(recording.delivered) == 1


def test_a_broken_evaluation_does_not_escape(session_factory):
    def broken_session_factory():
        raise RuntimeError("database is gone")

    evaluator = AlertService(
        broken_session_factory,
        settings=AlertSettings(),
        sink=RecordingSink(),
    )

    # The guarded path the worker thread actually calls.
    evaluator._guarded_evaluate()

    assert evaluator.current() == ([], None)


def test_the_worker_stops_without_waiting_out_its_interval(session_factory):
    evaluator = service(session_factory, RecordingSink(), interval_seconds=3600)

    evaluator.start()
    evaluator.stop(timeout=5)

    assert evaluator._thread is None


def test_logging_delivery_never_raises():
    """The default sink has to work under every condition, including an
    alert whose metric was not measurable."""

    LoggingAlertSink().deliver([_an_alert(value=None)])


def _an_alert(value: float | None = 0.5):
    from backend.observability.alerts import Alert, RuleState, Severity

    return Alert(
        key="error_rate",
        label="Requests are failing",
        severity=Severity.CRITICAL,
        state=RuleState.FIRING,
        value=value,
        threshold=0.1,
        advice="Check the error panel.",
        since=NOW,
    )
