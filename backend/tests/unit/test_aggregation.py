"""
The metric arithmetic.

Pure functions, so these tests need no database and no application - which
matters, because this is the layer where a quiet mistake would not crash
anything, it would just put a wrong number on a dashboard and be believed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.observability.aggregation import (
    NAMED_RANGES,
    SpanPoint,
    TimeWindow,
    TracePoint,
    UnknownTimeRangeError,
    bucket_series,
    percentile,
    summarize_latency,
    summarize_requests,
    summarize_stages,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def window(minutes: int = 60) -> TimeWindow:
    return TimeWindow(start=NOW - timedelta(minutes=minutes), end=NOW)


def trace(
    *,
    offset_minutes: float = 0.0,
    duration_ms: float = 100.0,
    status: str = "ok",
    status_code: int | None = 200,
    route: str = "/api/query",
) -> TracePoint:
    return TracePoint(
        started_at=NOW - timedelta(minutes=60) + timedelta(minutes=offset_minutes),
        duration_ms=duration_ms,
        status=status,
        status_code=status_code,
        route=route,
    )


# ----------------------------------------------------------------------
# Percentiles
# ----------------------------------------------------------------------


def test_percentile_interpolates_between_neighbours():
    values = [10.0, 20.0, 30.0, 40.0]

    # Position 0.5 * 3 = 1.5, halfway between 20 and 30.
    assert percentile(values, 0.5) == pytest.approx(25.0)


def test_percentile_endpoints_are_the_extremes():
    values = [5.0, 10.0, 90.0]

    assert percentile(values, 0.0) == 5.0
    assert percentile(values, 1.0) == 90.0


def test_percentile_of_one_value_is_that_value():
    assert percentile([42.0], 0.99) == 42.0


def test_percentile_of_nothing_is_undefined():
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_percentile_matches_postgres_percentile_cont():
    """
    Pinned against the definition percentile_cont uses, so moving this
    arithmetic into SQL later cannot silently shift every chart.

    For 1..10, percentile_cont(0.95) is 9.55.
    """

    values = [float(n) for n in range(1, 11)]

    assert percentile(values, 0.95) == pytest.approx(9.55)
    assert percentile(values, 0.5) == pytest.approx(5.5)


def test_latency_summary_reports_the_standard_points():
    summary = summarize_latency([float(n) for n in range(1, 101)])

    assert summary.count == 100
    assert set(summary.percentiles) == {"p50", "p75", "p90", "p95", "p99"}
    assert summary.p95 == pytest.approx(95.05)


def test_no_durations_means_no_percentiles_rather_than_zeros():
    """
    "Nothing happened" and "everything took no time" must not render the
    same way on a chart.
    """

    summary = summarize_latency([])

    assert summary.count == 0
    assert summary.percentiles == {}
    assert summary.p95 is None


# ----------------------------------------------------------------------
# Request rates
# ----------------------------------------------------------------------


def test_request_rates_are_per_window_length():
    points = [trace() for _ in range(120)]

    summary = summarize_requests(points, window(minutes=60))

    assert summary.total == 120
    assert summary.requests_per_minute == pytest.approx(2.0)
    assert summary.requests_per_second == pytest.approx(2.0 / 60.0)


def test_a_handled_5xx_counts_as_a_failure():
    """
    The subtle case. /api/query catches everything and returns 502, so the
    trace's own status stays "ok" - counting only trace-level errors would
    report a completely broken pipeline as a 100% success rate.
    """

    points = [
        trace(status_code=200),
        trace(status_code=502),
    ]

    summary = summarize_requests(points, window())

    assert summary.failed == 1
    assert summary.succeeded == 1
    assert summary.failure_rate == pytest.approx(0.5)


def test_an_unhandled_exception_counts_as_a_failure():
    """No response ever started, so there is no status code to judge by."""

    points = [trace(status="error", status_code=None)]

    summary = summarize_requests(points, window())

    assert summary.failed == 1
    assert summary.success_rate == 0.0


def test_client_errors_are_separated_from_failures():
    """
    A 401 is the auth layer working, not the service failing. Folding the
    two together would make every unauthenticated poll look like an outage.
    """

    points = [
        trace(status_code=200),
        trace(status_code=401),
        trace(status_code=404),
        trace(status_code=500),
    ]

    summary = summarize_requests(points, window())

    assert summary.succeeded == 1
    assert summary.client_errors == 2
    assert summary.failed == 1
    assert summary.client_error_rate == pytest.approx(0.5)


def test_an_empty_window_reports_zeroes_not_an_error():
    summary = summarize_requests([], window())

    assert summary.total == 0
    assert summary.success_rate == 0.0
    assert summary.latency.count == 0


# ----------------------------------------------------------------------
# Stages
# ----------------------------------------------------------------------


def test_stages_are_ordered_by_p95_slowest_first():
    points = [
        SpanPoint(stage="generation", duration_ms=2400.0, status="ok"),
        SpanPoint(stage="generation", duration_ms=2600.0, status="ok"),
        SpanPoint(stage="reranking", duration_ms=390.0, status="ok"),
        SpanPoint(stage="fusion", duration_ms=0.4, status="ok"),
    ]

    summaries = summarize_stages(points)

    # "Which stage is costing me the most" should be the first row.
    assert [summary.stage for summary in summaries] == [
        "generation",
        "reranking",
        "fusion",
    ]


def test_sub_millisecond_stages_are_not_rounded_away():
    summaries = summarize_stages(
        [SpanPoint(stage="fusion", duration_ms=0.42, status="ok")]
    )

    assert summaries[0].latency.p95 == pytest.approx(0.42)


def test_stage_error_rate_is_per_stage():
    points = [
        SpanPoint(stage="reranking", duration_ms=10.0, status="ok"),
        SpanPoint(stage="reranking", duration_ms=10.0, status="error"),
        SpanPoint(stage="generation", duration_ms=10.0, status="ok"),
    ]

    by_stage = {summary.stage: summary for summary in summarize_stages(points)}

    assert by_stage["reranking"].error_rate == pytest.approx(0.5)
    assert by_stage["generation"].error_rate == 0.0


# ----------------------------------------------------------------------
# Time series
# ----------------------------------------------------------------------


def test_series_covers_the_window_on_a_fixed_grid():
    series = bucket_series([], window(minutes=60), bucket=timedelta(minutes=10))

    assert len(series) == 6
    assert series[0].start == NOW - timedelta(minutes=60)
    assert series[-1].start == NOW - timedelta(minutes=10)


def test_empty_buckets_are_emitted_rather_than_skipped():
    """A gap in traffic is a finding; closing the gap would hide an outage."""

    points = [trace(offset_minutes=5), trace(offset_minutes=55)]

    series = bucket_series(points, window(minutes=60), bucket=timedelta(minutes=10))

    assert [bucket.total for bucket in series] == [1, 0, 0, 0, 0, 1]


def test_points_land_in_the_bucket_they_started_in():
    points = [
        trace(offset_minutes=0),
        trace(offset_minutes=9.9),
        trace(offset_minutes=10.1),
    ]

    series = bucket_series(points, window(minutes=60), bucket=timedelta(minutes=10))

    assert series[0].total == 2
    assert series[1].total == 1


def test_series_buckets_carry_their_own_status_split():
    points = [
        trace(offset_minutes=1, status_code=200),
        trace(offset_minutes=2, status_code=502),
        trace(offset_minutes=3, status_code=404),
    ]

    series = bucket_series(points, window(minutes=60), bucket=timedelta(minutes=10))

    assert series[0].succeeded == 1
    assert series[0].failed == 1
    assert series[0].client_errors == 1


# ----------------------------------------------------------------------
# Time windows
# ----------------------------------------------------------------------


def test_every_offered_range_resolves():
    for name in NAMED_RANGES:
        resolved = TimeWindow.named(name, now=NOW)

        assert resolved.end == NOW
        assert resolved.start < NOW


def test_an_unoffered_range_is_rejected():
    with pytest.raises(UnknownTimeRangeError):
        TimeWindow.named("7 years", now=NOW)


def test_bucket_size_grows_with_the_window():
    """
    Every range should render as a chart-sized number of points, not six
    for a day or twenty thousand for a month.
    """

    for name in NAMED_RANGES:
        resolved = TimeWindow.named(name, now=NOW)

        points = resolved.seconds / resolved.bucket_size().total_seconds()

        assert 20 <= points <= 90, f"{name} would render {points:.0f} points"
