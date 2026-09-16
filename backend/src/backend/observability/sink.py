"""
Background persistence for telemetry records.

The contract this file exists to satisfy is section 9 of the observability
spec: a monitoring failure must never become a RAG failure. Concretely,
`submit` never blocks and never raises - it drops on a full queue - and the
worker thread swallows every database error it meets. A request thread never
touches the database on telemetry's behalf.
"""

import logging
import queue
import threading
import uuid
from collections.abc import Iterable

from rag.observability.schemas import SpanRecord, TraceRecord
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import RagSpan, RagTrace
from backend.observability.config import TelemetryConfig

logger = logging.getLogger(__name__)

# Pushed onto the queue by stop() to wake the worker immediately rather than
# waiting out the flush interval.
_STOP = object()

Record = SpanRecord | TraceRecord


def _coerce_uuid(value: str | None):
    """
    Parse an id that should be a UUID, or give up quietly.

    A malformed conversation or user id must cost that one column, not the
    whole telemetry row - the trace is still worth keeping without it.
    """

    if not value:
        return None

    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


# Metadata keys the application stores as columns instead. Promoted here
# rather than added to TraceRecord, so the engine stays free of HTTP
# concepts - it records what happened, the application decides which of
# those facts deserve an index.
_PROMOTED_TRACE_KEYS = ("status_code", "route")


def _to_trace_row(record: TraceRecord) -> RagTrace:
    meta = dict(record.metadata or {})

    # Removed rather than copied, so a value never disagrees with itself.
    promoted = {key: meta.pop(key, None) for key in _PROMOTED_TRACE_KEYS}

    status_code = promoted["status_code"]

    return RagTrace(
        id=record.trace_id,
        status_code=status_code if isinstance(status_code, int) else None,
        route=str(promoted["route"])[:256] if promoted["route"] else None,
        request_id=record.request_id,
        conversation_id=_coerce_uuid(record.conversation_id),
        user_id=_coerce_uuid(record.user_id),
        status=record.status.value,
        error_type=record.error_type,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_ms=record.duration_ms,
        environment=record.environment,
        app_version=record.app_version,
        meta=meta or None,
    )


def _to_span_row(record: SpanRecord) -> RagSpan:
    return RagSpan(
        id=record.span_id,
        trace_id=record.trace_id,
        parent_span_id=record.parent_span_id,
        stage=record.stage,
        status=record.status.value,
        error_type=record.error_type,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_ms=record.duration_ms,
        meta=record.metadata or None,
    )


class BackgroundTelemetrySink:
    """
    A bounded queue drained by one daemon thread.

    Deliberately not a thread pool and not an async task: ingestion and the
    query path both run in worker threads already, and a single writer keeps
    the database side to one connection and one transaction per batch.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        config: TelemetryConfig,
    ) -> None:
        self._session_factory = session_factory
        self._config = config

        self._queue: queue.Queue = queue.Queue(maxsize=config.queue_size)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Counters, not metrics of their own: surfaced on the monitoring
        # dashboard later so a gap in the data is visible as a number rather
        # than inferred from missing rows.
        self._dropped = 0
        self._written = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._thread = threading.Thread(
                target=self._run,
                name="telemetry-writer",
                daemon=True,
            )

            self._thread.start()

        logger.info("Telemetry writer started.")

    def stop(self) -> None:
        """
        Drain what is queued and stop the worker.

        Bounded by shutdown_timeout_seconds: a database that has gone away
        must not hold up the application's shutdown.
        """

        with self._lock:
            thread = self._thread
            self._thread = None

        if thread is None:
            return

        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            logger.warning("Telemetry queue full at shutdown; some records are lost.")

        thread.join(timeout=self._config.shutdown_timeout_seconds)

        logger.info(
            "Telemetry writer stopped (written=%d, dropped=%d).",
            self._written,
            self._dropped,
        )

    # ------------------------------------------------------------------
    # Producer side - called on request threads
    # ------------------------------------------------------------------

    def submit(self, record: Record) -> None:
        """
        Hand a record to the writer. Never blocks, never raises.
        """

        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self._dropped += 1

            # One line per drop would itself become the incident; the
            # counter is the signal, so this only speaks up occasionally.
            if self._dropped % 100 == 1:
                logger.warning(
                    "Telemetry queue is full; dropped %d records so far.",
                    self._dropped,
                )
        except Exception:
            self._dropped += 1
            logger.exception("Failed to queue a telemetry record.")

    # ------------------------------------------------------------------
    # Consumer side - the worker thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        pending: list[Record] = []

        while True:
            try:
                item = self._queue.get(timeout=self._config.flush_interval_seconds)
            except queue.Empty:
                self._flush(pending)
                pending = []
                continue
            except Exception:
                logger.exception("Telemetry writer failed to read its queue.")
                return

            if item is _STOP:
                pending.extend(self._drain())
                self._flush(pending)
                return

            pending.append(item)

            if len(pending) >= self._config.batch_size:
                self._flush(pending)
                pending = []

    def _drain(self) -> list[Record]:
        remaining: list[Record] = []

        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return remaining

            if item is not _STOP:
                remaining.append(item)

    def _flush(self, records: Iterable[Record]) -> None:
        batch = list(records)

        if not batch:
            return

        rows = []

        for record in batch:
            try:
                if isinstance(record, TraceRecord):
                    rows.append(_to_trace_row(record))
                else:
                    rows.append(_to_span_row(record))
            except Exception:
                self._dropped += 1
                logger.exception("Failed to convert a telemetry record.")

        if not rows:
            return

        try:
            with self._session_factory() as session:
                session.add_all(rows)
                session.commit()

            self._written += len(rows)
        except Exception:
            # Not requeued: a persistent database problem would otherwise
            # recycle the same batch forever and starve newer records.
            self._dropped += len(rows)
            logger.exception("Failed to write %d telemetry records.", len(rows))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def written(self) -> int:
        return self._written

    def flush_now(self) -> None:
        """
        Drain the queue synchronously. For tests and for shutdown paths that
        need the rows visible immediately; not used on the request path.
        """

        self._flush(self._drain())
