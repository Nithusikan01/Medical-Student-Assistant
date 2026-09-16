"""
Operational metrics derived from trace and span rows.

Deliberately pure: every function here takes plain data and returns plain
data, so the metric arithmetic - which is the part that is easy to get
subtly wrong - is testable without a database, a clock, or an application.
The repository layer supplies the rows; this decides what they mean.

Everything here is an *online* metric in the sense of section 54: measured
from real traffic, no ground truth required. Nothing in this module makes a
claim about answer quality.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

DEFAULT_PERCENTILES = (50, 75, 90, 95, 99)

# Section 45's ranges. The bucket widths are chosen so every range renders
# as roughly 30-60 points: enough shape to see a spike, few enough to send
# to a browser without pagination.
NAMED_RANGES: dict[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

_BUCKET_FOR_RANGE: tuple[tuple[timedelta, timedelta], ...] = (
    (timedelta(minutes=15), timedelta(seconds=30)),
    (timedelta(hours=1), timedelta(minutes=1)),
    (timedelta(hours=6), timedelta(minutes=10)),
    (timedelta(hours=24), timedelta(minutes=30)),
    (timedelta(days=7), timedelta(hours=3)),
)

_FALLBACK_BUCKET = timedelta(hours=12)


class UnknownTimeRangeError(ValueError):
    """Raised for a range name that is not offered."""


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    @property
    def seconds(self) -> float:
        return max((self.end - self.start).total_seconds(), 0.0)

    @classmethod
    def named(cls, name: str, *, now: datetime | None = None) -> "TimeWindow":
        span = NAMED_RANGES.get(name)

        if span is None:
            raise UnknownTimeRangeError(name)

        end = now or datetime.now(UTC)

        return cls(start=end - span, end=end)

    def bucket_size(self) -> timedelta:
        span = self.end - self.start

        for limit, bucket in _BUCKET_FOR_RANGE:
            if span <= limit:
                return bucket

        return _FALLBACK_BUCKET


@dataclass(frozen=True, slots=True)
class TracePoint:
    """The columns of one trace that operational metrics need."""

    started_at: datetime
    duration_ms: float
    status: str
    status_code: int | None = None
    route: str | None = None


@dataclass(frozen=True, slots=True)
class SpanPoint:
    """The columns of one span that per-stage metrics need."""

    stage: str
    duration_ms: float
    status: str


@dataclass(frozen=True, slots=True)
class LatencySummary:
    count: int
    percentiles: dict[str, float] = field(default_factory=dict)

    @property
    def p95(self) -> float | None:
        return self.percentiles.get("p95")


@dataclass(frozen=True, slots=True)
class RequestSummary:
    total: int

    succeeded: int
    client_errors: int
    failed: int

    success_rate: float
    client_error_rate: float
    failure_rate: float

    requests_per_second: float
    requests_per_minute: float

    latency: LatencySummary


@dataclass(frozen=True, slots=True)
class StageSummary:
    stage: str
    count: int
    errors: int
    error_rate: float
    latency: LatencySummary


@dataclass(frozen=True, slots=True)
class SeriesBucket:
    start: datetime
    total: int
    succeeded: int
    client_errors: int
    failed: int
    p95_ms: float | None


# ----------------------------------------------------------------------
# Percentiles
# ----------------------------------------------------------------------


def percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """
    Linear-interpolation percentile over an already-sorted sequence.

    The same definition Postgres' percentile_cont uses, so a future move of
    this arithmetic into SQL - which is what section 46's rollups would
    want - produces the same numbers rather than a silent shift in every
    chart.
    """

    if not sorted_values:
        raise ValueError("percentile of an empty sequence is undefined")

    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (len(sorted_values) - 1) * min(max(fraction, 0.0), 1.0)

    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return float(sorted_values[lower])

    weight = position - lower

    return float(
        sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight
    )


def summarize_latency(
    durations: Iterable[float],
    *,
    wanted: Sequence[int] = DEFAULT_PERCENTILES,
) -> LatencySummary:
    """
    Percentiles of a set of durations.

    An empty input yields a count of zero and no percentiles at all, rather
    than zeros - "nothing happened" and "everything took no time" must not
    render identically on a chart.
    """

    values = sorted(float(duration) for duration in durations if duration is not None)

    if not values:
        return LatencySummary(count=0)

    return LatencySummary(
        count=len(values),
        percentiles={
            f"p{point}": percentile(values, point / 100.0) for point in wanted
        },
    )


# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------


def _is_failure(point: TracePoint) -> bool:
    """
    Whether a trace represents a request that failed.

    Three cases, and missing any one of them understates the failure rate:

    - the trace itself errored, meaning an exception escaped the router;
    - no status was ever recorded, which means no response started at all;
    - a 5xx response, which the router handled and therefore left the
      trace's own status as "ok".

    That last case is the subtle one. /api/query catches everything and
    returns 502, so a completely broken pipeline produces traces that are
    "ok" at the trace level and 502 at the HTTP level.
    """

    if point.status != "ok":
        return True

    if point.status_code is None:
        return True

    return point.status_code >= 500


def _is_client_error(point: TracePoint) -> bool:
    return (
        point.status == "ok"
        and point.status_code is not None
        and 400 <= point.status_code < 500
    )


def summarize_requests(
    points: Sequence[TracePoint],
    window: TimeWindow,
) -> RequestSummary:
    total = len(points)

    if total == 0:
        return RequestSummary(
            total=0,
            succeeded=0,
            client_errors=0,
            failed=0,
            success_rate=0.0,
            client_error_rate=0.0,
            failure_rate=0.0,
            requests_per_second=0.0,
            requests_per_minute=0.0,
            latency=LatencySummary(count=0),
        )

    failed = sum(1 for point in points if _is_failure(point))
    client_errors = sum(1 for point in points if _is_client_error(point))
    succeeded = total - failed - client_errors

    seconds = window.seconds or 1.0
    per_second = total / seconds

    return RequestSummary(
        total=total,
        succeeded=succeeded,
        client_errors=client_errors,
        failed=failed,
        success_rate=succeeded / total,
        client_error_rate=client_errors / total,
        failure_rate=failed / total,
        requests_per_second=per_second,
        requests_per_minute=per_second * 60.0,
        latency=summarize_latency(point.duration_ms for point in points),
    )


# ----------------------------------------------------------------------
# Stages
# ----------------------------------------------------------------------


def summarize_stages(points: Sequence[SpanPoint]) -> list[StageSummary]:
    """
    Per-stage latency and error rate, slowest stage first.

    Ordered by p95 rather than by name or by call order, because the
    question this answers is "which stage is costing me the most", and the
    answer should be the first row.
    """

    grouped: dict[str, list[SpanPoint]] = {}

    for point in points:
        grouped.setdefault(point.stage, []).append(point)

    summaries = []

    for stage, stage_points in grouped.items():
        errors = sum(1 for point in stage_points if point.status != "ok")

        summaries.append(
            StageSummary(
                stage=stage,
                count=len(stage_points),
                errors=errors,
                error_rate=errors / len(stage_points),
                latency=summarize_latency(point.duration_ms for point in stage_points),
            )
        )

    return sorted(
        summaries,
        key=lambda summary: summary.latency.p95 or 0.0,
        reverse=True,
    )


# ----------------------------------------------------------------------
# Time series
# ----------------------------------------------------------------------


def bucket_series(
    points: Sequence[TracePoint],
    window: TimeWindow,
    *,
    bucket: timedelta | None = None,
) -> list[SeriesBucket]:
    """
    Requests over time, on a fixed grid.

    Empty buckets are emitted rather than skipped: a gap in traffic is a
    finding, and a chart that simply closes the gap hides an outage.
    """

    size = bucket or window.bucket_size()
    seconds = size.total_seconds()

    if seconds <= 0 or window.seconds <= 0:
        return []

    count = math.ceil(window.seconds / seconds)
    buckets: list[list[TracePoint]] = [[] for _ in range(count)]

    for point in points:
        offset = (point.started_at - window.start).total_seconds()

        if offset < 0:
            continue

        index = int(offset // seconds)

        if 0 <= index < count:
            buckets[index].append(point)

    series = []

    for index, bucket_points in enumerate(buckets):
        failed = sum(1 for point in bucket_points if _is_failure(point))
        client_errors = sum(1 for point in bucket_points if _is_client_error(point))

        latency = summarize_latency(point.duration_ms for point in bucket_points)

        series.append(
            SeriesBucket(
                start=window.start + (size * index),
                total=len(bucket_points),
                succeeded=len(bucket_points) - failed - client_errors,
                client_errors=client_errors,
                failed=failed,
                p95_ms=latency.p95,
            )
        )

    return series
