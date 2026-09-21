"""
Turning metrics into something that says a thing is wrong.

Every number an alert here fires on already existed. What was missing was
anything that looked at them and said so, which meant the dashboard could
only be a place someone went *after* noticing a problem some other way.

Three rules shape this module.

**Thresholds are configuration.** Error rate, latency, spend and silence
all have defaults, and all of them are wrong for somebody. They are read
from the environment like everything else tunable here.

**An alert needs enough data to mean anything.** One request failing out
of one is a 100% error rate, and waking someone for it teaches them to
ignore the next page. Every rate rule carries a minimum sample size and
stays quiet below it - which is different from being satisfied: "not
enough data" is reported as its own state rather than as "healthy".

**Alerts clear on a lower bar than they fire on.** A metric sitting on
the threshold would otherwise fire, clear, fire and clear again, and a
flapping alert is noise wearing an alert's clothes.

This module is pure: it takes a snapshot of numbers and returns a
verdict. Gathering the snapshot and delivering the result live in
services/alerting.py, so the arithmetic is testable without a database,
a clock, or a webhook.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class RuleState(str, Enum):
    OK = "ok"
    FIRING = "firing"

    # Reported rather than folded into OK: a rule with nothing to judge
    # has not passed, it has not run. Collapsing the two would let a
    # service that stopped receiving traffic look healthy.
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class AlertRule:
    """
    One threshold, and the conditions under which it may speak.

    `clear_at` is the hysteresis floor: once firing, the metric has to
    come back below this - not merely below `threshold` - before the
    alert clears.
    """

    key: str
    label: str
    metric: str
    threshold: float
    clear_at: float

    severity: Severity = Severity.WARNING

    # Below this many observations the rule reports INSUFFICIENT_DATA.
    # Zero means the metric is not a rate and one sample is meaningful -
    # "no successful ingest for six hours" needs no sample size.
    min_samples: int = 0
    sample_metric: str | None = None

    # What to do about it. Carried on the rule so the notification says
    # something useful rather than restating the number.
    advice: str = ""

    def judge(self, snapshot: "Snapshot", *, firing: bool) -> RuleState:
        value = snapshot.get(self.metric)

        if value is None:
            return RuleState.INSUFFICIENT_DATA

        if self.min_samples:
            samples = snapshot.get(self.sample_metric or "", 0.0) or 0.0

            if samples < self.min_samples:
                return RuleState.INSUFFICIENT_DATA

        # Hysteresis: the bar to stay firing is lower than the bar to
        # start, so a metric hovering on the threshold does not flap.
        limit = self.clear_at if firing else self.threshold

        return RuleState.FIRING if value > limit else RuleState.OK


@dataclass(frozen=True, slots=True)
class Alert:
    """A rule's verdict at one moment."""

    key: str
    label: str
    severity: Severity
    state: RuleState

    value: float | None
    threshold: float
    advice: str

    since: datetime | None = None

    @property
    def firing(self) -> bool:
        return self.state is RuleState.FIRING


class Snapshot(dict):
    """
    The numbers one evaluation looks at.

    A plain mapping of metric name to value, where **None means "not
    measurable"** rather than zero - no requests in the window, no
    pricing configured, no ingest ever. Rules treat None as insufficient
    data instead of as a passing score.
    """

    def get_value(self, name: str) -> float | None:
        value = self.get(name)

        return float(value) if isinstance(value, int | float) else None


@dataclass
class AlertEvaluator:
    """
    Applies the rules, remembering what was already firing.

    The memory is what makes hysteresis and `since` possible; it lives
    for the life of the process, so a restart re-announces whatever is
    still wrong. That is the right way round: a missed clear is a small
    annoyance, a missed fire is the thing this exists to prevent.
    """

    rules: tuple[AlertRule, ...]

    _firing: dict[str, datetime] = field(default_factory=dict)

    def evaluate(self, snapshot: Snapshot, *, now: datetime) -> list[Alert]:
        results: list[Alert] = []

        for rule in self.rules:
            was_firing = rule.key in self._firing
            state = rule.judge(snapshot, firing=was_firing)

            if state is RuleState.FIRING:
                since = self._firing.setdefault(rule.key, now)
            else:
                since = None
                self._firing.pop(rule.key, None)

            results.append(
                Alert(
                    key=rule.key,
                    label=rule.label,
                    severity=rule.severity,
                    state=state,
                    value=snapshot.get_value(rule.metric),
                    threshold=rule.threshold,
                    advice=rule.advice,
                    since=since,
                )
            )

        return results

    def newly_firing(self, alerts: Iterable[Alert], *, now: datetime) -> list[Alert]:
        """
        The alerts that started firing on this pass.

        What a delivery sink should send: re-sending everything currently
        wrong on every tick is how an alerting system gets muted.
        """

        return [alert for alert in alerts if alert.firing and alert.since == now]


def build_rules(settings: "AlertSettings") -> tuple[AlertRule, ...]:
    """
    The rule set, built from configured thresholds.

    Each clears at 80% of its firing threshold - close enough that a
    genuinely recovered metric clears promptly, far enough that noise
    around the line does not flap.
    """

    def clear(value: float) -> float:
        return value * 0.8

    return (
        AlertRule(
            key="error_rate",
            label="Requests are failing",
            metric="error_rate",
            threshold=settings.error_rate,
            clear_at=clear(settings.error_rate),
            severity=Severity.CRITICAL,
            min_samples=settings.min_requests,
            sample_metric="requests",
            advice="Check the error panel for the category before the cause.",
        ),
        AlertRule(
            key="latency_p95",
            label="Answers are slow",
            metric="p95_ms",
            threshold=settings.p95_ms,
            clear_at=clear(settings.p95_ms),
            min_samples=settings.min_requests,
            sample_metric="requests",
            advice="The stage breakdown says which part got slower.",
        ),
        AlertRule(
            key="cost_per_hour",
            label="Spend is high",
            metric="cost_per_hour_usd",
            threshold=settings.cost_per_hour_usd,
            clear_at=clear(settings.cost_per_hour_usd),
            advice="Token usage by stage shows what is consuming it.",
        ),
        AlertRule(
            key="telemetry_drops",
            label="Telemetry is being dropped",
            metric="dropped_records",
            threshold=settings.dropped_records,
            clear_at=clear(settings.dropped_records),
            advice=(
                "The writer queue is full. Monitoring is lossy right now, so "
                "the other numbers on this page are understated."
            ),
        ),
        AlertRule(
            key="lexical_retrieval_empty",
            label="Lexical retrieval is returning nothing",
            metric="bm25_empty_rate",
            threshold=settings.bm25_empty_rate,
            clear_at=clear(settings.bm25_empty_rate),
            severity=Severity.CRITICAL,
            min_samples=settings.min_requests,
            sample_metric="bm25_calls",
            advice=(
                "Hybrid retrieval is running on one retriever with nothing "
                "failing. Check the knowledge base panel for unreachable "
                "chunks."
            ),
        ),
        AlertRule(
            key="stalled_ingestion",
            label="An ingestion is stuck",
            metric="stalled_documents",
            threshold=0.0,
            clear_at=0.0,
            advice="Delete the document and upload it again.",
        ),
    )


@dataclass(frozen=True)
class AlertSettings:
    """
    Thresholds. Every one of these is wrong for somebody, which is why
    none of them is a constant in the rules above.
    """

    enabled: bool = True

    error_rate: float = 0.10
    p95_ms: float = 15000.0
    cost_per_hour_usd: float = 1.0
    dropped_records: float = 0.0
    bm25_empty_rate: float = 0.5

    # Below this many requests in the window, the rate rules stay quiet.
    min_requests: int = 20

    interval_seconds: float = 300.0
    window_minutes: int = 15

    webhook_url: str | None = None

    def with_overrides(self, **overrides) -> "AlertSettings":
        return replace(self, **overrides)
