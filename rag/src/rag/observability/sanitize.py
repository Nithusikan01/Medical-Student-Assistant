"""
Metadata hygiene.

Two jobs, both mandated by sections 39 and 55 of the observability spec:
keep secrets out of telemetry, and keep telemetry small. Everything that
reaches a recorder passes through here, so a careless
`span.set(config=settings)` at some future call site cannot leak an API key
into a table that the monitoring dashboard then renders.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)

REDACTED = "[redacted]"
TRUNCATED_SUFFIX = "...[truncated]"

# Matching is deliberately three-part rather than one broad substring list.
# A bare "token" substring looks safer but redacts `prompt_tokens` and
# `total_tokens` - which would quietly make token accounting, the one thing
# this application already monitored, impossible to record. So: exact names
# that are always credentials, compound names that are always credentials,
# and singular suffixes. `user_token` is caught by the suffix rule;
# `total_tokens` is not, because it is plural.
SENSITIVE_EXACT_KEYS = frozenset(
    {
        "auth",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "key",
        "password",
        "passwd",
        "secret",
        "session",
        "token",
    }
)

SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "auth_token",
    "bearer",
    "private_key",
    "secret_key",
    "session_id",
    "password",
    "credential",
    "authorization",
)

SENSITIVE_KEY_SUFFIXES = (
    "_token",
    "_key",
    "_secret",
    "_password",
    "_credential",
)

MAX_STRING_LENGTH = 256
MAX_KEYS = 40
MAX_SEQUENCE_ITEMS = 20
MAX_DEPTH = 3


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()

    if lowered in SENSITIVE_EXACT_KEYS:
        return True

    if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
        return True

    return lowered.endswith(SENSITIVE_KEY_SUFFIXES)


def _truncate(text: str) -> str:
    if len(text) <= MAX_STRING_LENGTH:
        return text

    return text[:MAX_STRING_LENGTH] + TRUNCATED_SUFFIX


def _sanitize_value(value: Any, depth: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _truncate(value)

    if depth >= MAX_DEPTH:
        return _truncate(repr(value))

    if isinstance(value, Mapping):
        return _sanitize_mapping(value, depth + 1)

    # str and bytes are Sequences too, so they have to be handled above this.
    if isinstance(value, (list, tuple, set, frozenset)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        items = list(value)[:MAX_SEQUENCE_ITEMS]

        return [_sanitize_value(item, depth + 1) for item in items]

    return _truncate(repr(value))


def _sanitize_mapping(mapping: Mapping[str, Any], depth: int) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in list(mapping.items())[:MAX_KEYS]:
        name = str(key)

        result[name] = (
            REDACTED if _is_sensitive(name) else _sanitize_value(value, depth)
        )

    return result


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Return a copy safe to persist: redacted, truncated, and size-capped.

    Returns an empty dict rather than raising if sanitisation itself fails -
    losing one span's metadata is always preferable to failing the request
    that produced it.
    """

    if not metadata:
        return {}

    try:
        return _sanitize_mapping(metadata, depth=0)
    except Exception:
        logger.exception("Failed to sanitise telemetry metadata; dropping it.")
        return {}
