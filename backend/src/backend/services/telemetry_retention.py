"""
Ageing telemetry out of the database.

`TELEMETRY_RETENTION_DAYS` has been a setting since the telemetry tables
were added, and until now nothing read it. That is worse than having no
setting at all: a knob that appears to bound a table, and does not, reads
as handled from the outside while `rag_spans` grows without limit.

Two reasons this matters beyond disk. Cost, because these are by far the
highest-volume tables in the application - a span per stage, a dozen
stages per request. And privacy, because the spec asks for retention to
be configurable *and* enforced; span metadata is sanitised but not empty,
and "we keep it for thirty days" is only true if something deletes it.

Retention runs whether or not telemetry is enabled. Turning capture off
should still let what was already captured age out, rather than freezing
it in place for good.

Ordering. Spans are deleted by `trace_id` rather than by their own
timestamp, which matters for a request that straddles the cutoff: a trace
that started before it can own spans that started after it, and deleting
those spans by timestamp would leave them parented to nothing. Selecting
the traces first and deleting their spans by id keeps a trace and its
waterfall atomic - either both go or neither does.

Orphan spans are real and are swept separately. The sink drops records on
a full queue, and the trace row is written last, so a burst can leave
spans whose trace never arrived. Because a span cannot start before its
trace does, any span older than the cutoff once the trace sweep has
finished is an orphan by definition - which is why that sweep only runs
after the trace sweep has drained.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import RagSpan, RagTrace
from backend.observability.config import TelemetryConfig, load_telemetry_config

logger = logging.getLogger(__name__)

# Small enough that a first run against a table nobody has ever pruned
# does not hold one enormous transaction, or a lock, while it works.
DEFAULT_BATCH_SIZE = 500

# A guard against looping forever if rows keep arriving faster than they
# are deleted. Whatever is left is simply picked up on the next pass.
MAX_BATCHES = 200


@dataclass(frozen=True)
class PruneResult:
    """What one pass actually deleted."""

    traces: int = 0
    spans: int = 0
    orphan_spans: int = 0
    complete: bool = True

    @property
    def total(self) -> int:
        return self.traces + self.spans + self.orphan_spans

    def __bool__(self) -> bool:
        return self.total > 0


def _cutoff(retention_days: int, now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)) - timedelta(days=retention_days)


def _rowcount(result) -> int:
    count = getattr(result, "rowcount", 0)

    # -1 is what a driver returns when it does not know; treating that as a
    # number would make the log line fiction.
    return count if isinstance(count, int) and count > 0 else 0


def _prune_traces(
    session: Session,
    cutoff: datetime,
    batch_size: int,
) -> tuple[int, int, bool]:
    """One batch of traces and every span belonging to them."""

    ids = list(
        session.scalars(
            sa.select(RagTrace.id)
            .where(RagTrace.started_at < cutoff)
            .order_by(RagTrace.started_at)
            .limit(batch_size)
        ).all()
    )

    if not ids:
        return 0, 0, True

    spans = _rowcount(
        session.execute(sa.delete(RagSpan).where(RagSpan.trace_id.in_(ids)))
    )
    traces = _rowcount(session.execute(sa.delete(RagTrace).where(RagTrace.id.in_(ids))))

    session.commit()

    return traces, spans, len(ids) < batch_size


def _prune_orphan_spans(
    session: Session,
    cutoff: datetime,
    batch_size: int,
) -> tuple[int, bool]:
    ids = list(
        session.scalars(
            sa.select(RagSpan.id)
            .where(RagSpan.started_at < cutoff)
            .order_by(RagSpan.started_at)
            .limit(batch_size)
        ).all()
    )

    if not ids:
        return 0, True

    deleted = _rowcount(session.execute(sa.delete(RagSpan).where(RagSpan.id.in_(ids))))

    session.commit()

    return deleted, len(ids) < batch_size


def prune_telemetry(
    session_factory: sessionmaker[Session],
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = MAX_BATCHES,
) -> PruneResult:
    """
    Delete telemetry older than the retention window.

    Returns what was removed, so a caller can log it. Commits per batch:
    an interrupted run leaves less to do next time rather than nothing.
    """

    days = (
        retention_days
        if retention_days is not None
        else load_telemetry_config().retention_days
    )

    cutoff = _cutoff(days, now)

    traces = spans = orphans = 0
    drained = False

    with session_factory() as session:
        for _ in range(max_batches):
            batch_traces, batch_spans, last = _prune_traces(session, cutoff, batch_size)

            traces += batch_traces
            spans += batch_spans

            if last:
                drained = True
                break

        # Only once no trace below the cutoff is left: while the sweep above
        # is still working, a span older than the cutoff may well belong to a
        # trace that has not been reached yet, and deleting it would gut a
        # waterfall that is still meant to exist.
        if drained:
            for _ in range(max_batches):
                batch_orphans, last = _prune_orphan_spans(session, cutoff, batch_size)

                orphans += batch_orphans

                if last:
                    break

    return PruneResult(
        traces=traces,
        spans=spans,
        orphan_spans=orphans,
        complete=drained,
    )


def prune_on_startup(
    session_factory: sessionmaker[Session],
    *,
    retention_days: int | None = None,
) -> PruneResult:
    """
    Guarded wrapper for the lifespan.

    Same rule the rest of the telemetry layer follows: a problem deleting
    old rows must not stop the application starting.
    """

    try:
        result = prune_telemetry(session_factory, retention_days=retention_days)

        if result:
            logger.info(
                "Telemetry retention removed %d trace(s), %d span(s) and "
                "%d orphan span(s).",
                result.traces,
                result.spans,
                result.orphan_spans,
            )

        if not result.complete:
            logger.warning(
                "Telemetry retention stopped before draining; the remainder "
                "will be picked up on the next pass."
            )

        return result
    except Exception:
        logger.exception("Could not prune telemetry.")
        return PruneResult(complete=False)


class RetentionWorker:
    """
    Runs the sweep periodically, on a daemon thread.

    Startup alone is not enough on a long-lived task: a process that stays
    up for weeks would never age anything out. Daemon, like the telemetry
    writer, so it can never hold up interpreter shutdown.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        retention_days: int,
        interval_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._retention_days = retention_days
        self._interval_seconds = max(float(interval_seconds), 1.0)

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run,
            name="telemetry-retention",
            daemon=True,
        )

        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()

        thread = self._thread
        self._thread = None

        if thread is not None:
            thread.join(timeout=timeout)

    def _run(self) -> None:
        # Waits before the first pass on purpose: the lifespan has already
        # swept once by the time this thread starts.
        while not self._stop.wait(self._interval_seconds):
            prune_on_startup(
                self._session_factory,
                retention_days=self._retention_days,
            )


def start_retention_worker(
    session_factory: sessionmaker[Session],
    config: TelemetryConfig | None = None,
) -> RetentionWorker | None:
    """
    Sweep once now, then keep sweeping. Never raises.

    Deliberately not conditional on `config.enabled`: switching capture off
    should let what is already stored age out, not freeze it there.
    """

    settings = config or load_telemetry_config()

    prune_on_startup(session_factory, retention_days=settings.retention_days)

    try:
        worker = RetentionWorker(
            session_factory,
            retention_days=settings.retention_days,
            interval_seconds=settings.retention_interval_hours * 3600.0,
        )

        worker.start()

        return worker
    except Exception:
        logger.exception("Could not start the telemetry retention worker.")
        return None
