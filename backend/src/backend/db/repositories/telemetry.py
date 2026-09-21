"""
Reads over the telemetry tables.

Each function fetches exactly the columns the metric layer needs and
nothing else - never whole rows, and never the JSON metadata, which is by
far the widest column and is only wanted when a single trace is being
inspected.

A note on where the arithmetic happens. Percentiles are computed in Python
from a durations-only fetch rather than by `percentile_cont` in SQL. At
this application's traffic - a class of students - a window holds
thousands of rows at most, and one portable code path that the SQLite test
suite genuinely exercises is worth more than SQL that only production
would ever run. Section 46's hourly rollups are the answer if the volume
ever changes; `count_traces` exists so a caller can see the size of a
window before asking for it.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import RagSpan, RagTrace
from backend.observability.aggregation import SpanPoint, TimeWindow, TracePoint


def _within(window: TimeWindow):
    return sa.and_(
        RagTrace.started_at >= window.start,
        RagTrace.started_at < window.end,
    )


def count_traces(session: Session, window: TimeWindow) -> int:
    return int(
        session.scalar(
            sa.select(sa.func.count()).select_from(RagTrace).where(_within(window))
        )
        or 0
    )


def trace_points(
    session: Session,
    window: TimeWindow,
    *,
    route: str | None = None,
    environment: str | None = None,
) -> list[TracePoint]:
    query = sa.select(
        RagTrace.started_at,
        RagTrace.duration_ms,
        RagTrace.status,
        RagTrace.status_code,
        RagTrace.route,
    ).where(_within(window))

    if route is not None:
        query = query.where(RagTrace.route == route)

    if environment is not None:
        query = query.where(RagTrace.environment == environment)

    return [
        TracePoint(
            started_at=started_at,
            duration_ms=float(duration_ms),
            status=status,
            status_code=status_code,
            route=row_route,
        )
        for started_at, duration_ms, status, status_code, row_route in session.execute(
            query.order_by(RagTrace.started_at)
        )
    ]


def span_points(
    session: Session,
    window: TimeWindow,
    *,
    stage: str | None = None,
    stages: Sequence[str] | None = None,
) -> list[SpanPoint]:
    query = sa.select(
        RagSpan.stage,
        RagSpan.duration_ms,
        RagSpan.status,
    ).where(
        sa.and_(
            RagSpan.started_at >= window.start,
            RagSpan.started_at < window.end,
        )
    )

    if stage is not None:
        query = query.where(RagSpan.stage == stage)

    # A family of stages rather than one - the ingestion panel wants every
    # ingestion stage and nothing else, and filtering in SQL beats pulling
    # a window's worth of query spans to discard them in Python.
    if stages is not None:
        query = query.where(RagSpan.stage.in_(list(stages)))

    return [
        SpanPoint(
            stage=row_stage,
            duration_ms=float(duration_ms),
            status=status,
        )
        for row_stage, duration_ms, status in session.execute(query)
    ]


def error_counts_by_type(
    session: Session,
    window: TimeWindow,
    *,
    limit: int = 20,
) -> list[tuple[str, str, int]]:
    """
    (stage, error_type, count) for failed spans, most frequent first.

    Aggregated in SQL rather than in Python: unlike the percentile paths
    this is a genuine GROUP BY with a small, bounded result, so there is
    nothing to gain from moving the rows.
    """

    rows = session.execute(
        sa.select(
            RagSpan.stage,
            RagSpan.error_type,
            sa.func.count().label("total"),
        )
        .where(
            sa.and_(
                RagSpan.started_at >= window.start,
                RagSpan.started_at < window.end,
                RagSpan.status != "ok",
            )
        )
        .group_by(RagSpan.stage, RagSpan.error_type)
        .order_by(sa.desc("total"))
        .limit(limit)
    )

    return [
        (stage, error_type or "unknown", int(total))
        for stage, error_type, total in rows
    ]


def route_counts(
    session: Session,
    window: TimeWindow,
) -> list[tuple[str, int]]:
    """(route, count) over the window, busiest first."""

    rows = session.execute(
        sa.select(RagTrace.route, sa.func.count().label("total"))
        .where(_within(window))
        .group_by(RagTrace.route)
        .order_by(sa.desc("total"))
    )

    return [(route or "unmatched", int(total)) for route, total in rows]


def span_metadata(
    session: Session,
    window: TimeWindow,
    *,
    stages: Sequence[str],
) -> list[tuple[str, dict]]:
    """
    (stage, metadata) for the named stages within the window.

    The retrieval numbers - counts, scores, overlap, rank change - live in
    each span's JSON metadata rather than in columns, so unlike the latency
    paths this cannot be a GROUP BY. Fetching stage and metadata only, and
    summarising in Python, keeps one portable code path the SQLite suite
    genuinely exercises; promoting a dozen retrieval fields to columns to
    aggregate them in SQL would be a lot of schema for numbers nobody
    filters on.

    The same volume ceiling as the percentile paths applies, and the same
    answer: section 46's rollups, if it ever matters.
    """

    if not stages:
        return []

    rows = session.execute(
        sa.select(RagSpan.stage, RagSpan.meta).where(
            sa.and_(
                RagSpan.started_at >= window.start,
                RagSpan.started_at < window.end,
                RagSpan.stage.in_(list(stages)),
            )
        )
    )

    return [(stage, meta or {}) for stage, meta in rows]


# ----------------------------------------------------------------------
# The trace explorer's reads
# ----------------------------------------------------------------------


def list_traces(
    session: Session,
    window: TimeWindow,
    *,
    limit: int = 50,
    before: datetime | None = None,
    route: str | None = None,
    failed_only: bool = False,
    conversation_id: uuid.UUID | None = None,
) -> list[RagTrace]:
    """
    Recent traces, newest first.

    Paged by a `before` cursor on started_at rather than by OFFSET: traces
    arrive continuously, and an offset would skip or repeat rows as the
    table grows underneath the reader.

    `failed_only` covers the same three cases the metric layer treats as a
    failure - an errored trace, a trace with no status at all, and a 5xx -
    because the subtle one is a handled 502, where the trace's own status
    is still "ok".
    """

    query = sa.select(RagTrace).where(_within(window))

    if before is not None:
        query = query.where(RagTrace.started_at < before)

    if route is not None:
        query = query.where(RagTrace.route == route)

    if conversation_id is not None:
        query = query.where(RagTrace.conversation_id == conversation_id)

    if failed_only:
        query = query.where(
            sa.or_(
                RagTrace.status != "ok",
                RagTrace.status_code.is_(None),
                RagTrace.status_code >= 500,
            )
        )

    return list(
        session.scalars(query.order_by(RagTrace.started_at.desc()).limit(limit)).all()
    )


def get_trace(session: Session, trace_id: str) -> RagTrace | None:
    return session.get(RagTrace, trace_id)


def spans_for_trace(session: Session, trace_id: str) -> list[RagSpan]:
    """
    One trace's spans in waterfall order.

    Ordered by `sequence`, not `started_at`: the wall clock ties between a
    parent span and the child it opens, so ordering by time renders the
    waterfall scrambled.
    """

    return list(
        session.scalars(
            sa.select(RagSpan)
            .where(RagSpan.trace_id == trace_id)
            .order_by(RagSpan.sequence, RagSpan.started_at)
        ).all()
    )


def find_trace_ids_for_conversation(
    session: Session,
    conversation_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[str]:
    """Every trace belonging to one conversation, newest first."""

    return list(
        session.scalars(
            sa.select(RagTrace.id)
            .where(RagTrace.conversation_id == conversation_id)
            .order_by(RagTrace.started_at.desc())
            .limit(limit)
        ).all()
    )
