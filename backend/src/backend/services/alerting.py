"""
Gathering the numbers, judging them, and telling someone.

The arithmetic is in observability/alerts.py and stays pure. This module
does the three things that need the outside world: read the metrics,
run the evaluator on a timer, and deliver what changed.

Delivery sits behind a protocol, like every other seam in this project.
Logging is the default because it always works and costs nothing; a
webhook is configuration. Neither may raise - an alerting system that
takes the application down with it has inverted its own purpose.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session, sessionmaker

from backend.db.repositories import documents as document_repo
from backend.db.repositories import telemetry as telemetry_repo
from backend.db.repositories import usage as usage_repo
from backend.observability.aggregation import (
    TimeWindow,
    summarize_requests,
)
from backend.observability.alerts import (
    Alert,
    AlertEvaluator,
    AlertSettings,
    Snapshot,
    build_rules,
)
from backend.observability.config import load_alert_settings
from backend.observability.retrieval_metrics import build_report
from backend.services.ingest_recovery import stall_threshold

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5.0


@runtime_checkable
class AlertSink(Protocol):
    """Somewhere to send alerts. Implementations must never raise."""

    def deliver(self, alerts: Sequence[Alert]) -> None: ...


class LoggingAlertSink:
    """
    The default, and the one that always works.

    Deliberately not configurable away: whatever else is wired up, an
    alert that fired should be findable in the logs afterwards.
    """

    def deliver(self, alerts: Sequence[Alert]) -> None:
        for alert in alerts:
            logger.warning(
                "ALERT %s (%s): %s is %.4g, over %.4g. %s",
                alert.key,
                alert.severity.value,
                alert.label,
                alert.value if alert.value is not None else float("nan"),
                alert.threshold,
                alert.advice,
            )


class WebhookAlertSink:
    """
    Posts a small JSON body to a configured URL.

    stdlib rather than a client library: this is one POST, and a new
    runtime dependency for it would be a poor trade. Failure is logged
    and swallowed - a webhook nobody is listening to must not become an
    exception in the evaluator.
    """

    def __init__(self, url: str, timeout: float = WEBHOOK_TIMEOUT_SECONDS) -> None:
        self._url = url
        self._timeout = timeout

    def deliver(self, alerts: Sequence[Alert]) -> None:
        if not alerts:
            return

        payload = {
            "alerts": [
                {
                    "key": alert.key,
                    "label": alert.label,
                    "severity": alert.severity.value,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "advice": alert.advice,
                    "since": alert.since.isoformat() if alert.since else None,
                }
                for alert in alerts
            ]
        }

        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout):
                return
        except (urllib.error.URLError, OSError, ValueError):
            logger.exception("Could not deliver alerts to the webhook.")


class FanOutSink:
    """Every sink gets the alert, and one failing does not stop the rest."""

    def __init__(self, sinks: Sequence[AlertSink]) -> None:
        self._sinks = list(sinks)

    def deliver(self, alerts: Sequence[Alert]) -> None:
        for sink in self._sinks:
            try:
                sink.deliver(alerts)
            except Exception:
                logger.exception("An alert sink failed.")


# ----------------------------------------------------------------------
# Gathering
# ----------------------------------------------------------------------


def gather_snapshot(
    session: Session,
    *,
    window: TimeWindow,
    dropped_records: int = 0,
) -> Snapshot:
    """
    Every number the rules judge, read once.

    Absent values stay absent. A window with no requests has no error
    rate and no p95 - reporting either as zero would let an outage that
    stopped all traffic read as perfect health.
    """

    traces = telemetry_repo.trace_points(session, window)
    requests = summarize_requests(traces, window)

    retrieval = build_report(
        telemetry_repo.span_metadata(
            session,
            window,
            stages=("bm25_retrieval",),
        )
    )

    bm25 = next(
        (row for row in retrieval.retrievers if row.stage == "bm25_retrieval"),
        None,
    )

    totals = usage_repo.totals_between(session, window.start, window.end)

    priced = sum(int(row[6] or 0) for row in totals["by_model"])
    cost = sum(float(row[5] or 0) for row in totals["by_model"]) if priced else None

    hours = window.seconds / 3600.0

    snapshot = Snapshot(
        {
            "requests": float(requests.total),
            # Null, not zero, when nothing ran: an empty window is not a
            # passing grade.
            "error_rate": requests.failure_rate if requests.total else None,
            "p95_ms": requests.latency.percentiles.get("p95"),
            # Null when no model in the window has a pricing row. "Not
            # priced" must never be charted as "free".
            "cost_per_hour_usd": (cost / hours) if cost is not None and hours else None,
            "dropped_records": float(dropped_records),
            "bm25_calls": float(bm25.calls) if bm25 else 0.0,
            "bm25_empty_rate": bm25.empty_rate if bm25 and bm25.calls else None,
            "stalled_documents": float(
                document_repo.count_processing_since(
                    session,
                    datetime.now(UTC) - stall_threshold(),
                )
            ),
        }
    )

    return snapshot


# ----------------------------------------------------------------------
# The service
# ----------------------------------------------------------------------


class AlertService:
    """
    Evaluates on a timer and holds the latest verdict.

    The endpoint reads `current()` rather than evaluating on request:
    a dashboard refresh should not be able to decide whether an alert
    fires, and several admins watching at once should see one answer.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        settings: AlertSettings | None = None,
        sink: AlertSink | None = None,
        drop_count: "callable | None" = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings or load_alert_settings()
        self._evaluator = AlertEvaluator(rules=build_rules(self._settings))
        self._sink = sink or self._build_sink()
        self._drop_count = drop_count

        self._alerts: list[Alert] = []
        self._evaluated_at: datetime | None = None
        self._lock = threading.Lock()

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _build_sink(self) -> AlertSink:
        sinks: list[AlertSink] = [LoggingAlertSink()]

        if self._settings.webhook_url:
            sinks.append(WebhookAlertSink(self._settings.webhook_url))

        return FanOutSink(sinks)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_once(self, *, now: datetime | None = None) -> list[Alert]:
        moment = now or datetime.now(UTC)

        window = TimeWindow(
            start=moment - timedelta(minutes=self._settings.window_minutes),
            end=moment,
        )

        with self._session_factory() as session:
            snapshot = gather_snapshot(
                session,
                window=window,
                dropped_records=self._dropped(),
            )

        alerts = self._evaluator.evaluate(snapshot, now=moment)

        with self._lock:
            self._alerts = alerts
            self._evaluated_at = moment

        # Only what started firing on this pass. Re-sending everything
        # currently wrong on every tick is how an alerting system gets
        # muted.
        started = self._evaluator.newly_firing(alerts, now=moment)

        if started:
            self._sink.deliver(started)

        return alerts

    def _dropped(self) -> int:
        if self._drop_count is None:
            return 0

        try:
            return int(self._drop_count())
        except Exception:
            # The sink may not be running. Not knowing how many records
            # were dropped is not itself worth an alert.
            logger.exception("Could not read the telemetry drop count.")
            return 0

    def current(self) -> tuple[list[Alert], datetime | None]:
        with self._lock:
            return list(self._alerts), self._evaluated_at

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None or not self._settings.enabled:
            return

        self._thread = threading.Thread(
            target=self._run,
            name="alert-evaluator",
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
        # Evaluated immediately rather than after one interval: a service
        # that comes up already broken should say so now.
        self._guarded_evaluate()

        while not self._stop.wait(self._settings.interval_seconds):
            self._guarded_evaluate()

    def _guarded_evaluate(self) -> None:
        try:
            self.evaluate_once()
        except Exception:
            logger.exception("Could not evaluate alerts.")


def start_alert_service(
    session_factory: sessionmaker[Session],
    *,
    drop_count=None,
) -> AlertService | None:
    """Never raises: alerting must not be able to stop the application."""

    try:
        service = AlertService(session_factory, drop_count=drop_count)
        service.start()

        return service
    except Exception:
        logger.exception("Could not start the alert evaluator.")
        return None
