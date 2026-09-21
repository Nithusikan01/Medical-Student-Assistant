"""
Reads over the telemetry tables.

The last test is the one that matters most: it writes through the real
tracer and sink, then reads back through the repository and the metric
layer. Everything in between - the metadata promotion into columns, the
timezone handling, the window boundaries - is only proven by going the
whole way.
"""

from datetime import UTC, datetime, timedelta

import pytest
from rag.observability import Stage, Tracer
from sqlalchemy.orm import Session

from backend.db.models import RagSpan, RagTrace
from backend.db.repositories import telemetry as repo
from backend.observability.aggregation import (
    TimeWindow,
    summarize_requests,
    summarize_stages,
)
from backend.observability.config import TelemetryConfig
from backend.observability.recorder import PersistentTraceRecorder
from backend.observability.retrieval_metrics import RETRIEVAL_STAGES, build_report
from backend.observability.sink import BackgroundTelemetrySink

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def window() -> TimeWindow:
    return TimeWindow(start=NOW - timedelta(hours=1), end=NOW)


def add_trace(
    db: Session,
    *,
    trace_id: str,
    minutes_ago: float = 30.0,
    duration_ms: float = 100.0,
    status: str = "ok",
    status_code: int | None = 200,
    route: str = "/api/query",
    environment: str = "test",
) -> None:
    started = NOW - timedelta(minutes=minutes_ago)

    db.add(
        RagTrace(
            id=trace_id,
            status=status,
            status_code=status_code,
            route=route,
            environment=environment,
            started_at=started,
            ended_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
        )
    )
    db.commit()


def add_span(
    db: Session,
    *,
    span_id: str,
    stage: str,
    duration_ms: float = 50.0,
    status: str = "ok",
    error_type: str | None = None,
    minutes_ago: float = 30.0,
) -> None:
    started = NOW - timedelta(minutes=minutes_ago)

    db.add(
        RagSpan(
            id=span_id,
            trace_id="trace-1",
            stage=stage,
            status=status,
            error_type=error_type,
            started_at=started,
            ended_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
        )
    )
    db.commit()


# ----------------------------------------------------------------------
# Windowing
# ----------------------------------------------------------------------


def test_only_traces_inside_the_window_are_returned(db, window):
    add_trace(db, trace_id="inside", minutes_ago=30)
    add_trace(db, trace_id="too-old", minutes_ago=90)

    points = repo.trace_points(db, window)

    assert len(points) == 1
    assert points[0].duration_ms == 100.0


def test_the_window_end_is_exclusive(db, window):
    """
    Half-open, so consecutive windows neither double-count a trace nor drop
    one between them.
    """

    add_trace(db, trace_id="at-end", minutes_ago=0)
    add_trace(db, trace_id="at-start", minutes_ago=60)

    points = repo.trace_points(db, window)

    assert len(points) == 1


def test_traces_come_back_in_start_order(db, window):
    add_trace(db, trace_id="second", minutes_ago=10)
    add_trace(db, trace_id="first", minutes_ago=50)

    points = repo.trace_points(db, window)

    assert points[0].started_at < points[1].started_at


def test_counting_a_window_does_not_fetch_it(db, window):
    for index in range(5):
        add_trace(db, trace_id=f"trace-{index}")

    assert repo.count_traces(db, window) == 5


# ----------------------------------------------------------------------
# Filtering
# ----------------------------------------------------------------------


def test_traces_can_be_filtered_by_route(db, window):
    add_trace(db, trace_id="query", route="/api/query")
    add_trace(db, trace_id="conversations", route="/api/conversations")

    points = repo.trace_points(db, window, route="/api/query")

    assert [point.route for point in points] == ["/api/query"]


def test_traces_can_be_filtered_by_environment(db, window):
    add_trace(db, trace_id="prod", environment="production")
    add_trace(db, trace_id="dev", environment="development")

    assert len(repo.trace_points(db, window, environment="production")) == 1


def test_route_counts_are_busiest_first(db, window):
    add_trace(db, trace_id="a", route="/api/query")
    add_trace(db, trace_id="b", route="/api/query")
    add_trace(db, trace_id="c", route="/api/conversations")

    assert repo.route_counts(db, window) == [
        ("/api/query", 2),
        ("/api/conversations", 1),
    ]


def test_an_unmatched_route_is_labelled_rather_than_dropped(db, window):
    add_trace(db, trace_id="404", route=None, status_code=404)

    assert repo.route_counts(db, window) == [("unmatched", 1)]


# ----------------------------------------------------------------------
# Spans
# ----------------------------------------------------------------------


def test_span_points_can_be_narrowed_to_one_stage(db, window):
    add_span(db, span_id="s1", stage="generation", duration_ms=2000.0)
    add_span(db, span_id="s2", stage="reranking", duration_ms=300.0)

    points = repo.span_points(db, window, stage="generation")

    assert [point.stage for point in points] == ["generation"]


def test_error_counts_group_by_stage_and_type(db, window):
    add_span(db, span_id="e1", stage="generation", status="error", error_type="Timeout")
    add_span(db, span_id="e2", stage="generation", status="error", error_type="Timeout")
    add_span(
        db,
        span_id="e3",
        stage="reranking",
        status="error",
        error_type="RuntimeError",
    )
    add_span(db, span_id="ok", stage="generation")

    counts = repo.error_counts_by_type(db, window)

    assert counts[0] == ("generation", "Timeout", 2)
    assert ("reranking", "RuntimeError", 1) in counts

    # Successful spans are not errors.
    assert sum(total for _, _, total in counts) == 3


def test_a_missing_error_type_is_labelled_unknown(db, window):
    add_span(db, span_id="e1", stage="generation", status="error", error_type=None)

    assert repo.error_counts_by_type(db, window) == [("generation", "unknown", 1)]


# ----------------------------------------------------------------------
# The whole path
# ----------------------------------------------------------------------


def test_metrics_can_be_computed_from_what_the_tracer_actually_writes(
    db,
    session_factory,
):
    """
    Tracer -> recorder -> sink -> columns -> repository -> metrics.

    In particular this is what proves status_code and route reach their new
    columns: they are set as span metadata by the middleware and promoted
    by the sink, so nothing short of the full path would catch a break.
    """

    sink = BackgroundTelemetrySink(session_factory, TelemetryConfig())
    tracer = Tracer(PersistentTraceRecorder(sink), environment="test")

    for status_code in (200, 200, 502):
        with (
            tracer.trace(route="/api/query", status_code=status_code),
            tracer.span(Stage.GENERATION),
        ):
            pass

    sink.flush_now()

    window = TimeWindow(
        start=datetime.now(UTC) - timedelta(minutes=5),
        end=datetime.now(UTC) + timedelta(minutes=5),
    )

    summary = summarize_requests(repo.trace_points(db, window), window)

    assert summary.total == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert summary.latency.p95 is not None

    stages = summarize_stages(repo.span_points(db, window))

    assert [stage.stage for stage in stages] == ["generation"]
    assert stages[0].count == 3

    # Promoted onto columns, and therefore no longer duplicated in the JSON.
    stored = db.get(RagTrace, next(iter(db.query(RagTrace.id).all()))[0])

    assert stored.route == "/api/query"
    assert stored.status_code in {200, 502}
    assert "status_code" not in (stored.meta or {})
    assert "route" not in (stored.meta or {})


# ----------------------------------------------------------------------
# Retrieval metadata
# ----------------------------------------------------------------------


def add_span_with_meta(db, *, span_id, stage, meta, minutes_ago=30.0):
    started = NOW - timedelta(minutes=minutes_ago)

    db.add(
        RagSpan(
            id=span_id,
            trace_id="trace-1",
            stage=stage,
            status="ok",
            started_at=started,
            ended_at=started + timedelta(milliseconds=5),
            duration_ms=5.0,
            meta=meta,
        )
    )
    db.commit()


def test_span_metadata_is_fetched_for_the_named_stages(db, window):
    add_span_with_meta(
        db,
        span_id="d1",
        stage="dense_retrieval",
        meta={"result_count": 30, "top_score": 0.9},
    )
    add_span_with_meta(
        db, span_id="b1", stage="bm25_retrieval", meta={"result_count": 0}
    )
    add_span_with_meta(db, span_id="g1", stage="generation", meta={"total_tokens": 100})

    rows = repo.span_metadata(db, window, stages=RETRIEVAL_STAGES)

    assert {stage for stage, _ in rows} == {"dense_retrieval", "bm25_retrieval"}


def test_asking_for_no_stages_queries_nothing(db, window):
    add_span_with_meta(db, span_id="d1", stage="dense_retrieval", meta={})

    assert repo.span_metadata(db, window, stages=[]) == []


def test_a_span_with_no_metadata_comes_back_as_an_empty_dict(db, window):
    add_span_with_meta(db, span_id="d1", stage="dense_retrieval", meta=None)

    assert repo.span_metadata(db, window, stages=["dense_retrieval"]) == [
        ("dense_retrieval", {})
    ]


def test_a_retrieval_report_can_be_built_from_stored_spans(db, window):
    """The whole path: spans in the database out to a retrieval report."""

    add_span_with_meta(
        db,
        span_id="d1",
        stage="dense_retrieval",
        meta={"result_count": 30, "top_score": 0.9, "average_score": 0.5},
    )
    add_span_with_meta(
        db, span_id="b1", stage="bm25_retrieval", meta={"result_count": 0}
    )
    add_span_with_meta(
        db,
        span_id="f1",
        stage="fusion",
        meta={"dense_count": 30, "bm25_count": 0, "dense_only_count": 30},
    )
    add_span_with_meta(
        db,
        span_id="r1",
        stage="reranking",
        meta={
            "candidate_count": 30,
            "final_count": 5,
            "reranker_used": "PineconeReranker",
            "reranker_degraded": False,
            "introduced_count": 3,
            "reordered_count": 5,
        },
    )

    report = build_report(repo.span_metadata(db, window, stages=RETRIEVAL_STAGES))

    by_stage = {r.stage: r for r in report.retrievers}

    assert by_stage["bm25_retrieval"].empty_rate == 1.0
    assert report.fusion.single_retriever_rate == 1.0
    assert report.reranking.change_rate == 1.0
    assert report.reranking.degraded_rate == 0.0
