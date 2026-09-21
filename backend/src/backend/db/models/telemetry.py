import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

STATUS_OK = "ok"
STATUS_ERROR = "error"

TELEMETRY_STATUSES = (STATUS_OK, STATUS_ERROR)


class RagTrace(Base):
    """
    One end-to-end request.

    Deliberately carries no foreign keys, unlike every other table here.
    Telemetry is written asynchronously and in batches, so a row can arrive
    after the conversation or user it refers to has been deleted - a real
    constraint would then fail the whole batch and lose unrelated traces
    with it. The ids are still stored (and indexed) for joining; they are
    just not enforced.
    """

    __tablename__ = "rag_traces"

    # A 32-character hex id, not a Uuid column: it matches OpenTelemetry's
    # trace id shape, so these rows can be exported to an OTel backend later
    # without re-keying anything.
    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)

    request_id: Mapped[str | None] = mapped_column(sa.String(64))

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)

    status: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default=STATUS_OK,
        server_default=STATUS_OK,
    )

    error_type: Mapped[str | None] = mapped_column(sa.String(128))

    # What kind of failure, as opposed to which exception class. A column
    # rather than a metadata key because the error panel groups by it, and
    # an alert on "rate limited" has to be able to filter in SQL.
    error_category: Mapped[str | None] = mapped_column(sa.String(32))

    # Promoted out of `meta` into columns because both are primary
    # dashboard dimensions - success and error rates group by status class,
    # and per-route latency groups by route. Querying them inside a JSON
    # column would need dialect-specific SQL, which the SQLite-backed test
    # suite could not exercise.
    #
    # Nullable on purpose: an exception that escapes past the router means
    # no response ever starts, so there is no status to record. That case
    # counts as a failure, which is why "no status" and 5xx are treated
    # alike when rates are computed.
    status_code: Mapped[int | None] = mapped_column(sa.Integer)

    # The route template, never the concrete path - one series per route
    # rather than one per conversation id.
    route: Mapped[str | None] = mapped_column(sa.String(256))

    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    # Float rather than Integer: the fast stages (fusion, context building)
    # finish well inside a millisecond, and rounding them to 0 would make
    # per-stage latency charts lie about where time actually goes.
    duration_ms: Mapped[float] = mapped_column(sa.Float, nullable=False)

    environment: Mapped[str | None] = mapped_column(sa.String(32))
    app_version: Mapped[str | None] = mapped_column(sa.String(32))

    # "metadata" is reserved on a declarative class, hence the shorter name
    # on both the attribute and the column.
    meta: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)

    __table_args__ = (
        sa.CheckConstraint(
            f"status IN ('{STATUS_OK}', '{STATUS_ERROR}')",
            name="status_valid",
        ),
        # Every dashboard query is "recent traces, newest first", optionally
        # narrowed by status.
        sa.Index("ix_rag_traces_started_at", "started_at"),
        sa.Index("ix_rag_traces_status_started_at", "status", "started_at"),
        sa.Index("ix_rag_traces_conversation_id", "conversation_id"),
        sa.Index("ix_rag_traces_user_id", "user_id"),
        sa.Index("ix_rag_traces_route_started_at", "route", "started_at"),
    )


class RagSpan(Base):
    """
    One stage of work inside a trace.

    `trace_id` has no foreign key to rag_traces on purpose: spans are
    emitted as each stage completes and the trace row is written only when
    the request finishes, so the child rows legitimately exist before the
    parent.
    """

    __tablename__ = "rag_spans"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)

    trace_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(sa.String(64))

    stage: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # Position within the trace, 1-based, handed out by a monotonic counter
    # when the span opens. This is the ordering key for a waterfall, because
    # started_at does not work: the wall clock is coarser than the gap
    # between a parent span and the child it opens, so retrieval,
    # dense_retrieval and query_embedding routinely share one timestamp to
    # the microsecond and render out of order.
    sequence: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    status: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default=STATUS_OK,
        server_default=STATUS_OK,
    )

    error_type: Mapped[str | None] = mapped_column(sa.String(128))
    error_category: Mapped[str | None] = mapped_column(sa.String(32))

    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    duration_ms: Mapped[float] = mapped_column(sa.Float, nullable=False)

    meta: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)

    __table_args__ = (
        sa.CheckConstraint(
            f"status IN ('{STATUS_OK}', '{STATUS_ERROR}')",
            name="status_valid",
        ),
        # The trace explorer reads one trace's spans in start order; the
        # per-stage latency panels aggregate one stage across a time window.
        # The trace explorer reads one trace's spans in waterfall order.
        sa.Index("ix_rag_spans_trace_id_sequence", "trace_id", "sequence"),
        sa.Index("ix_rag_spans_stage_started_at", "stage", "started_at"),
        # Retention sweeps orphan spans by age alone - spans whose trace row
        # never arrived, because the sink drops on a full queue and the
        # trace is written last. The composite above cannot serve that
        # query: started_at is not its leading column.
        sa.Index("ix_rag_spans_started_at", "started_at"),
        # "What kind of thing is failing, over this window" - the error
        # panel's only query.
        sa.Index("ix_rag_spans_error_category", "error_category", "started_at"),
    )
