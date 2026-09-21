"""
Turning metrics into something that says a thing is wrong.

Three properties are asserted repeatedly here because getting any of
them wrong produces an alerting system people mute:

  - a rate with too few samples behind it says so, rather than firing
  - "not measurable" is not "healthy"
  - an alert clears on a lower bar than it fires on, so it cannot flap
"""

from datetime import UTC, datetime, timedelta

import pytest

from backend.observability.alerts import (
    AlertEvaluator,
    AlertRule,
    AlertSettings,
    RuleState,
    Severity,
    Snapshot,
    build_rules,
)
from backend.observability.config import load_alert_settings

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

SETTINGS = AlertSettings(min_requests=20)


def evaluator(**overrides) -> AlertEvaluator:
    return AlertEvaluator(rules=build_rules(SETTINGS.with_overrides(**overrides)))


def alert_for(alerts, key):
    return next(alert for alert in alerts if alert.key == key)


def snapshot(**values) -> Snapshot:
    base = {
        "requests": 100.0,
        "error_rate": 0.0,
        "p95_ms": 500.0,
        "cost_per_hour_usd": 0.0,
        "dropped_records": 0.0,
        "bm25_calls": 100.0,
        "bm25_empty_rate": 0.0,
        "stalled_documents": 0.0,
    }

    base.update(values)

    return Snapshot(base)


# ----------------------------------------------------------------------
# Firing
# ----------------------------------------------------------------------


def test_a_metric_over_its_threshold_fires():
    alerts = evaluator().evaluate(snapshot(error_rate=0.5), now=NOW)

    assert alert_for(alerts, "error_rate").firing


def test_a_healthy_metric_does_not_fire():
    alerts = evaluator().evaluate(snapshot(), now=NOW)

    assert not any(alert.firing for alert in alerts)


def test_the_threshold_is_exclusive():
    """Exactly at the threshold is not over it."""

    alerts = evaluator(error_rate=0.10).evaluate(snapshot(error_rate=0.10), now=NOW)

    assert not alert_for(alerts, "error_rate").firing


def test_a_firing_alert_carries_advice_not_just_a_number():
    """
    The number is already on the dashboard. What the alert adds is what
    to do about it.
    """

    alerts = evaluator().evaluate(snapshot(error_rate=0.9), now=NOW)

    assert alert_for(alerts, "error_rate").advice


def test_a_single_stuck_ingestion_fires():
    """
    Not a rate, so no sample-size floor applies: one document stuck is
    the whole finding.
    """

    alerts = evaluator().evaluate(snapshot(stalled_documents=1.0), now=NOW)

    assert alert_for(alerts, "stalled_ingestion").firing


def test_lexical_retrieval_silence_is_critical():
    """
    The failure this whole upgrade found once already: hybrid retrieval
    running on one retriever with nothing raising.
    """

    alerts = evaluator().evaluate(snapshot(bm25_empty_rate=1.0), now=NOW)

    alert = alert_for(alerts, "lexical_retrieval_empty")

    assert alert.firing
    assert alert.severity is Severity.CRITICAL


# ----------------------------------------------------------------------
# Not enough to go on
# ----------------------------------------------------------------------


def test_a_rate_over_too_few_requests_stays_quiet():
    """
    One request failing out of one is a 100% error rate. Waking someone
    for it teaches them to ignore the next page.
    """

    alerts = evaluator().evaluate(
        snapshot(requests=1.0, error_rate=1.0),
        now=NOW,
    )

    assert alert_for(alerts, "error_rate").state is RuleState.INSUFFICIENT_DATA


def test_insufficient_data_is_not_reported_as_healthy():
    """
    Collapsing the two would let a service that stopped receiving traffic
    entirely look perfectly well.
    """

    alerts = evaluator().evaluate(snapshot(requests=0.0, error_rate=None), now=NOW)

    assert alert_for(alerts, "error_rate").state is RuleState.INSUFFICIENT_DATA


def test_an_unmeasurable_metric_does_not_fire():
    """Null is not zero, and it is not a breach either."""

    alerts = evaluator().evaluate(snapshot(cost_per_hour_usd=None), now=NOW)

    alert = alert_for(alerts, "cost_per_hour")

    assert alert.state is RuleState.INSUFFICIENT_DATA
    assert alert.value is None


def test_the_sample_floor_is_configurable():
    alerts = evaluator(min_requests=1).evaluate(
        snapshot(requests=1.0, error_rate=1.0),
        now=NOW,
    )

    assert alert_for(alerts, "error_rate").firing


# ----------------------------------------------------------------------
# Hysteresis
# ----------------------------------------------------------------------


def test_an_alert_does_not_clear_the_moment_it_dips_under():
    """
    A metric hovering on the threshold would otherwise fire, clear, fire
    and clear again - noise wearing an alert's clothes.
    """

    state = evaluator(error_rate=0.10)

    assert alert_for(
        state.evaluate(snapshot(error_rate=0.2), now=NOW), "error_rate"
    ).firing

    # Under the firing threshold, but not under the clear threshold.
    still = state.evaluate(snapshot(error_rate=0.09), now=NOW)

    assert alert_for(still, "error_rate").firing


def test_a_recovered_metric_clears():
    state = evaluator(error_rate=0.10)

    state.evaluate(snapshot(error_rate=0.5), now=NOW)

    cleared = state.evaluate(snapshot(error_rate=0.01), now=NOW)

    assert not alert_for(cleared, "error_rate").firing


def test_the_time_it_started_is_kept_across_evaluations():
    state = evaluator()
    later = NOW + timedelta(minutes=5)

    state.evaluate(snapshot(error_rate=0.5), now=NOW)
    second = state.evaluate(snapshot(error_rate=0.5), now=later)

    assert alert_for(second, "error_rate").since == NOW


def test_only_newly_firing_alerts_are_delivered():
    """
    Re-sending everything currently wrong on every tick is how an
    alerting system gets muted.
    """

    state = evaluator()
    later = NOW + timedelta(minutes=5)

    first = state.evaluate(snapshot(error_rate=0.5), now=NOW)
    assert len(state.newly_firing(first, now=NOW)) == 1

    second = state.evaluate(snapshot(error_rate=0.5), now=later)
    assert state.newly_firing(second, now=later) == []


def test_an_alert_that_cleared_can_fire_again():
    state = evaluator()
    later = NOW + timedelta(minutes=10)

    state.evaluate(snapshot(error_rate=0.5), now=NOW)
    state.evaluate(snapshot(error_rate=0.0), now=NOW + timedelta(minutes=5))

    again = state.evaluate(snapshot(error_rate=0.5), now=later)

    assert alert_for(again, "error_rate").since == later


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("variable", "attribute", "raw", "expected"),
    [
        ("ALERT_ERROR_RATE", "error_rate", "0.25", 0.25),
        ("ALERT_P95_MS", "p95_ms", "9000", 9000.0),
        ("ALERT_COST_PER_HOUR_USD", "cost_per_hour_usd", "5", 5.0),
        ("ALERT_MIN_REQUESTS", "min_requests", "50", 50),
        ("ALERT_WINDOW_MINUTES", "window_minutes", "30", 30),
    ],
)
def test_every_threshold_is_configurable(
    monkeypatch, variable, attribute, raw, expected
):
    monkeypatch.setenv(variable, raw)

    assert getattr(load_alert_settings(), attribute) == expected


def test_alerting_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "false")

    assert load_alert_settings().enabled is False


def test_no_webhook_configured_is_none_not_empty_string(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "   ")

    assert load_alert_settings().webhook_url is None


def test_rules_clear_below_where_they_fire():
    """The invariant hysteresis depends on, checked for every rule."""

    for rule in build_rules(SETTINGS):
        assert rule.clear_at <= rule.threshold


def test_a_rule_with_no_metric_in_the_snapshot_is_not_a_breach():
    rule = AlertRule(
        key="missing",
        label="Nothing measures this",
        metric="not_collected",
        threshold=1.0,
        clear_at=0.8,
    )

    assert rule.judge(Snapshot({}), firing=False) is RuleState.INSUFFICIENT_DATA
