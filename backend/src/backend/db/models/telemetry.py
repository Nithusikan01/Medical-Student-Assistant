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

    status: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default=STATUS_OK,
        server_default=STATUS_OK,
    )

    error_type: Mapped[str | None] = mapped_column(sa.String(128))

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
        sa.Index("ix_rag_spans_trace_id_started_at", "trace_id", "started_at"),
        sa.Index("ix_rag_spans_stage_started_at", "stage", "started_at"),
    )
