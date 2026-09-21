"""
Telemetry configuration.

Read from the environment like every other configurable in this application
(see rag/config/settings.py and backend/auth/config.py). Retention, sampling
and raw-text capture are settings rather than constants because sections 39,
41 and 52 of the observability spec require them to be tunable per
deployment.
"""

import logging
import os
from dataclasses import dataclass

from backend.observability.alerts import AlertSettings

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return max(int(raw), minimum)
    except ValueError:
        logger.warning("%s is not an integer; using %d.", name, default)
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return max(float(raw), minimum)
    except ValueError:
        logger.warning("%s is not a number; using %s.", name, default)
        return default


@dataclass(frozen=True)
class TelemetryConfig:
    # The master switch. Off means no tracer, no worker thread, no writes -
    # the application behaves exactly as it did before this phase.
    enabled: bool = True

    # 1.0 traces everything, which is right for a class-sized user base.
    sample_rate: float = 1.0

    # Bounded on purpose: under a burst, telemetry drops records rather than
    # growing memory or slowing the request that produced them.
    queue_size: int = 2000

    batch_size: int = 100
    flush_interval_seconds: float = 1.0
    shutdown_timeout_seconds: float = 5.0

    # Off by default. When enabled, instrumented stages may attach query and
    # answer text to their spans; otherwise only hashes, counts and scores
    # are stored (spec section 39).
    capture_text: bool = False

    # Enforced by backend/services/telemetry_retention.py, which deletes
    # anything older on startup and then once per interval.
    retention_days: int = 30
    retention_interval_hours: int = 24

    environment: str = "development"
    app_version: str = "2.0.0"


def load_telemetry_config() -> TelemetryConfig:
    sample_rate = _env_float("TELEMETRY_SAMPLE_RATE", 1.0)

    return TelemetryConfig(
        enabled=_env_bool("TELEMETRY_ENABLED", True),
        sample_rate=min(sample_rate, 1.0),
        queue_size=_env_int("TELEMETRY_QUEUE_SIZE", 2000, minimum=1),
        batch_size=_env_int("TELEMETRY_BATCH_SIZE", 100, minimum=1),
        flush_interval_seconds=_env_float(
            "TELEMETRY_FLUSH_INTERVAL_SECONDS",
            1.0,
            minimum=0.05,
        ),
        shutdown_timeout_seconds=_env_float(
            "TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS",
            5.0,
            minimum=0.0,
        ),
        capture_text=_env_bool("TELEMETRY_CAPTURE_TEXT", False),
        retention_days=_env_int("TELEMETRY_RETENTION_DAYS", 30, minimum=1),
        retention_interval_hours=_env_int(
            "TELEMETRY_RETENTION_INTERVAL_HOURS",
            24,
            minimum=1,
        ),
        environment=os.getenv("APP_ENV", "development"),
        app_version=os.getenv("APP_VERSION", "2.0.0"),
    )


def _env_str(name: str) -> str | None:
    raw = os.getenv(name)

    return raw.strip() or None if raw else None


def load_alert_settings() -> AlertSettings:
    """
    Alert thresholds, from the environment.

    Every one of these defaults is wrong for somebody, which is why none
    of them is a constant in the rules. See backend/.env.example for what
    each one means and when to move it.
    """

    return AlertSettings(
        enabled=_env_bool("ALERTS_ENABLED", True),
        error_rate=_env_float("ALERT_ERROR_RATE", 0.10),
        p95_ms=_env_float("ALERT_P95_MS", 15000.0),
        cost_per_hour_usd=_env_float("ALERT_COST_PER_HOUR_USD", 1.0),
        dropped_records=_env_float("ALERT_DROPPED_RECORDS", 0.0),
        bm25_empty_rate=_env_float("ALERT_BM25_EMPTY_RATE", 0.5),
        min_requests=_env_int("ALERT_MIN_REQUESTS", 20, minimum=1),
        interval_seconds=_env_float("ALERT_INTERVAL_SECONDS", 300.0, minimum=10.0),
        window_minutes=_env_int("ALERT_WINDOW_MINUTES", 15, minimum=1),
        webhook_url=_env_str("ALERT_WEBHOOK_URL"),
    )
