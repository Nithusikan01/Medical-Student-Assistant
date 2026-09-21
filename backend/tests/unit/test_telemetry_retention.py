"""
Ageing telemetry out of the database.

These exist because the setting shipped long before the enforcement did:
TELEMETRY_RETENTION_DAYS was parsed, defaulted and then read by nothing,
so `rag_spans` grew without bound while the configuration said otherwise.
"""

from datetime import UTC, datetime, timedelta

from backend.db.models import RagSpan, RagTrace
from backend.observability.config import load_telemetry_config
from backend.services.telemetry_retention import (
    RetentionWorker,
    prune_on_startup,
    prune_telemetry,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def add_trace(
    db,
    *,
    trace_id: str,
    days_ago: float,
    spans: int = 0,
    span_offset_minutes: float = 0.0,
) -> str:
    started = NOW - timedelta(days=days_ago)

    db.add(
        RagTrace(
            id=trace_id,
            status="ok",
            started_at=started,
            ended_at=started + timedelta(seconds=1),
            duration_ms=1000.0,
        )
    )

    for index in range(spans):
        add_span(
            db,
            span_id=f"{trace_id}_span_{index}",
            trace_id=trace_id,
            started_at=started + timedelta(minutes=span_offset_minutes),
        )

    db.commit()

    return trace_id


def add_span(db, *, span_id: str, trace_id: str, started_at: datetime) -> None:
    db.add(
        RagSpan(
            id=span_id,
            trace_id=trace_id,
            stage="retrieval",
            sequence=1,
            status="ok",
            started_at=started_at,
            ended_at=started_at + timedelta(milliseconds=50),
            duration_ms=50.0,
        )
    )


def trace_ids(db) -> set[str]:
    return {trace.id for trace in db.query(RagTrace).all()}


def span_ids(db) -> set[str]:
    return {span.id for span in db.query(RagSpan).all()}


# ----------------------------------------------------------------------
# What gets deleted
# ----------------------------------------------------------------------


def test_traces_past_the_window_are_deleted(db, session_factory):
    add_trace(db, trace_id="old", days_ago=40)

    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert result.traces == 1

    db.expire_all()
    assert trace_ids(db) == set()


def test_traces_inside_the_window_are_kept(db, session_factory):
    add_trace(db, trace_id="recent", days_ago=3)

    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert result.traces == 0

    db.expire_all()
    assert trace_ids(db) == {"recent"}


def test_a_traces_spans_go_with_it(db, session_factory):
    add_trace(db, trace_id="old", days_ago=40, spans=3)
    add_trace(db, trace_id="recent", days_ago=1, spans=2)

    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert (result.traces, result.spans) == (1, 3)

    db.expire_all()
    assert trace_ids(db) == {"recent"}
    assert span_ids(db) == {"recent_span_0", "recent_span_1"}


def test_the_boundary_is_the_cutoff_not_a_round_day(db, session_factory):
    """A trace one minute the wrong side of the window still goes."""

    add_trace(db, trace_id="just_past", days_ago=30.001)
    add_trace(db, trace_id="just_inside", days_ago=29.999)

    prune_telemetry(session_factory, retention_days=30, now=NOW)

    db.expire_all()
    assert trace_ids(db) == {"just_inside"}


# ----------------------------------------------------------------------
# The cases that make the ordering matter
# ----------------------------------------------------------------------


def test_a_trace_straddling_the_cutoff_takes_its_whole_waterfall(db, session_factory):
    """
    Spans are deleted by trace_id, never by their own timestamp.

    A long request can start before the cutoff and emit spans after it.
    Sweeping spans by age would delete the trace and strand the later
    spans with no parent; by trace_id, the two go together.
    """

    add_trace(
        db,
        trace_id="straddler",
        days_ago=30.01,
        spans=2,
        # Comfortably the other side of the cutoff from its own trace.
        span_offset_minutes=60,
    )

    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert (result.traces, result.spans) == (1, 2)

    db.expire_all()
    assert span_ids(db) == set()


def test_orphan_spans_are_swept(db, session_factory):
    """
    The sink drops on a full queue and writes the trace last, so spans
    whose trace never arrived are a real state, not a hypothetical.
    """

    add_span(
        db,
        span_id="orphan",
        trace_id="trace_that_never_landed",
        started_at=NOW - timedelta(days=40),
    )
    db.commit()

    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert result.orphan_spans == 1

    db.expire_all()
    assert span_ids(db) == set()


def test_a_recent_orphan_span_is_kept(db, session_factory):
    add_span(
        db,
        span_id="recent_orphan",
        trace_id="trace_that_never_landed",
        started_at=NOW - timedelta(days=2),
    )
    db.commit()

    prune_telemetry(session_factory, retention_days=30, now=NOW)

    db.expire_all()
    assert span_ids(db) == {"recent_orphan"}


def test_orphans_are_not_swept_while_traces_remain(db, session_factory):
    """
    The orphan sweep deletes spans by age alone, so it is only safe once
    no trace below the cutoff is left. Stopping the trace sweep early
    must not let it run and gut a waterfall that still has its trace.
    """

    for index in range(4):
        add_trace(db, trace_id=f"old_{index}", days_ago=40, spans=1)

    result = prune_telemetry(
        session_factory,
        retention_days=30,
        now=NOW,
        batch_size=1,
        max_batches=2,
    )

    assert result.complete is False
    assert result.orphan_spans == 0

    db.expire_all()

    # The traces that survived this pass still have their spans.
    surviving = trace_ids(db)
    assert surviving
    assert span_ids(db) == {f"{trace_id}_span_0" for trace_id in surviving}


# ----------------------------------------------------------------------
# Batching
# ----------------------------------------------------------------------


def test_a_large_backlog_is_cleared_across_batches(db, session_factory):
    for index in range(7):
        add_trace(db, trace_id=f"old_{index}", days_ago=40, spans=1)

    result = prune_telemetry(session_factory, retention_days=30, now=NOW, batch_size=2)

    assert (result.traces, result.spans, result.complete) == (7, 7, True)

    db.expire_all()
    assert trace_ids(db) == set()
    assert span_ids(db) == set()


def test_nothing_to_do_is_not_an_error(db, session_factory):
    result = prune_telemetry(session_factory, retention_days=30, now=NOW)

    assert bool(result) is False
    assert result.total == 0
    assert result.complete is True


# ----------------------------------------------------------------------
# Configuration and guarding
# ----------------------------------------------------------------------


def test_the_window_is_configurable(monkeypatch):
    monkeypatch.setenv("TELEMETRY_RETENTION_DAYS", "7")

    assert load_telemetry_config().retention_days == 7


def test_the_sweep_interval_is_configurable(monkeypatch):
    monkeypatch.setenv("TELEMETRY_RETENTION_INTERVAL_HOURS", "6")

    assert load_telemetry_config().retention_interval_hours == 6


def test_the_configured_window_is_used_when_none_is_passed(
    db, session_factory, monkeypatch
):
    monkeypatch.setenv("TELEMETRY_RETENTION_DAYS", "1")

    add_trace(db, trace_id="two_days_old", days_ago=2)

    # No explicit retention_days: it has to read the setting, which is the
    # whole point of this phase.
    result = prune_telemetry(session_factory)

    assert result.traces == 1


def test_startup_pruning_never_stops_the_application():
    def broken_session_factory():
        raise RuntimeError("database is gone")

    result = prune_on_startup(broken_session_factory)

    assert result.total == 0


def test_the_worker_stops_cleanly_without_ever_sweeping(session_factory):
    """
    A long interval must not make shutdown wait for it: stop() sets the
    event the wait is blocked on rather than waiting it out.
    """

    worker = RetentionWorker(
        session_factory,
        retention_days=30,
        interval_seconds=3600,
    )

    worker.start()
    worker.stop(timeout=5)

    assert worker._thread is None
