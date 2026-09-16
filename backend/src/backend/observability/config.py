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

    retention_days: int = 30

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
        environment=os.getenv("APP_ENV", "development"),
        app_version=os.getenv("APP_VERSION", "2.0.0"),
    )
