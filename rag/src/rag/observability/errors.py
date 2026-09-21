"""
What kind of failure this was.

`/monitoring/errors` could already say how many requests failed and which
stage they failed in. It could not say what *kind* of failure was
happening, and that is the only part that changes what an operator does
next: a Gemini 429 means wait or raise a quota, a Pinecone timeout means
check a provider's status page, a malformed PDF means go and look at one
document. All three landed in one undifferentiated bucket.

Classification is by exception type and status code, never by matching
text in the message. Two reasons, and the second is the important one:

  - Provider messages change without notice, so a substring rule is a
    silent regression waiting to happen.
  - Provider messages carry secrets. A rejected request often echoes the
    key or the endpoint it was sent with, and a classifier that reads
    messages is one careless log line away from storing them. Nothing
    here ever returns a message, and the caller never stores one.

Type *names* are matched where the class itself cannot be imported - the
SDKs are optional dependencies, and importing google.api_core or groq
inside the engine to do an isinstance check would break `rag`'s rule of
staying free of application dependencies. A name is a stable part of an
SDK's public API in a way a message is not.
"""

import logging
from datetime import timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """
    Why a request failed, at the granularity an operator acts on.

    Deliberately short. A taxonomy with thirty entries is a taxonomy
    nobody reads; these are the distinctions that lead to different
    actions.
    """

    # The provider refused because we asked too often. Wait, back off, or
    # raise a quota.
    RATE_LIMIT = "rate_limit"

    # The provider took too long. Usually transient.
    TIMEOUT = "timeout"

    # The provider was reachable and failed, or was not reachable at all.
    UPSTREAM = "upstream"

    # Our credentials were rejected. Never transient - a key expired, was
    # rotated, or was never right.
    AUTH = "auth"

    # The input was not acceptable: a malformed PDF, a request the
    # provider rejected as invalid. The document or the request is at
    # fault, not the service.
    VALIDATION = "validation"

    # Everything else, which in practice means our own bug.
    INTERNAL = "internal"


# Exception class names, matched exactly. Drawn from the SDKs this
# application actually calls - google.api_core, groq, pinecone, httpx - so
# an entry here is a name one of them really raises rather than a guess at
# what an HTTP client might be called.
_NAMES: dict[str, ErrorCategory] = {
    # Rate limiting
    "ResourceExhausted": ErrorCategory.RATE_LIMIT,
    "RateLimitError": ErrorCategory.RATE_LIMIT,
    "TooManyRequests": ErrorCategory.RATE_LIMIT,
    "QuotaExceeded": ErrorCategory.RATE_LIMIT,
    # Timeouts
    "DeadlineExceeded": ErrorCategory.TIMEOUT,
    "Timeout": ErrorCategory.TIMEOUT,
    "TimeoutError": ErrorCategory.TIMEOUT,
    "ReadTimeout": ErrorCategory.TIMEOUT,
    "ConnectTimeout": ErrorCategory.TIMEOUT,
    "APITimeoutError": ErrorCategory.TIMEOUT,
    "PoolTimeout": ErrorCategory.TIMEOUT,
    # Upstream
    "ServiceUnavailable": ErrorCategory.UPSTREAM,
    "InternalServerError": ErrorCategory.UPSTREAM,
    "APIConnectionError": ErrorCategory.UPSTREAM,
    "APIStatusError": ErrorCategory.UPSTREAM,
    "ConnectError": ErrorCategory.UPSTREAM,
    "ConnectionError": ErrorCategory.UPSTREAM,
    "RemoteProtocolError": ErrorCategory.UPSTREAM,
    "PineconeApiException": ErrorCategory.UPSTREAM,
    "ServiceException": ErrorCategory.UPSTREAM,
    # Auth
    "Unauthenticated": ErrorCategory.AUTH,
    "PermissionDenied": ErrorCategory.AUTH,
    "AuthenticationError": ErrorCategory.AUTH,
    "PermissionDeniedError": ErrorCategory.AUTH,
    "Forbidden": ErrorCategory.AUTH,
    "Unauthorized": ErrorCategory.AUTH,
    # Validation
    "InvalidArgument": ErrorCategory.VALIDATION,
    "BadRequestError": ErrorCategory.VALIDATION,
    "BadRequest": ErrorCategory.VALIDATION,
    "UnprocessableEntityError": ErrorCategory.VALIDATION,
    "ValidationError": ErrorCategory.VALIDATION,
    "PdfReadError": ErrorCategory.VALIDATION,
    "PdfStreamError": ErrorCategory.VALIDATION,
    "EmptyFileError": ErrorCategory.VALIDATION,
}

# Built-in types, checked with isinstance so subclasses are caught too.
_BUILTINS: tuple[tuple[type, ErrorCategory], ...] = (
    (TimeoutError, ErrorCategory.TIMEOUT),
    (ConnectionError, ErrorCategory.UPSTREAM),
)

# Attributes an SDK might expose the HTTP status on. Checked in order.
_STATUS_ATTRIBUTES = ("status_code", "http_status", "status", "code")

# Attributes carrying "wait this long before retrying".
_RETRY_ATTRIBUTES = ("retry_after", "retry_delay", "retry_after_seconds")


def _from_status(status: int) -> ErrorCategory | None:
    if status == 429:
        return ErrorCategory.RATE_LIMIT

    if status in (401, 403):
        return ErrorCategory.AUTH

    if status in (408, 504):
        return ErrorCategory.TIMEOUT

    if 400 <= status < 500:
        return ErrorCategory.VALIDATION

    if status >= 500:
        return ErrorCategory.UPSTREAM

    return None


def status_code_of(error: BaseException) -> int | None:
    """The HTTP status an exception carries, if it carries one."""

    for name in _STATUS_ATTRIBUTES:
        value = getattr(error, name, None)

        # A bool is an int in Python, and only something in HTTP range is
        # meaningful as a status.
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 100 <= value < 600
        ):
            return value

    return None


def retry_after_of(error: BaseException) -> float | None:
    """
    How long the provider asked us to wait, when it says so.

    Worth recording separately from the category: "rate limited" and "rate
    limited, come back in 60 seconds" call for different responses, and
    the second is the only one that can be acted on automatically.
    """

    for name in _RETRY_ATTRIBUTES:
        value = getattr(error, name, None)

        if isinstance(value, bool):
            continue

        if isinstance(value, int | float) and value >= 0:
            return float(value)

        # google.api_core hands back a timedelta rather than a number.
        if isinstance(value, timedelta):
            return value.total_seconds()

    return None


def classify(error: BaseException) -> ErrorCategory:
    """
    What kind of failure this is. Never raises, never reads the message.

    Status code first, because it is the provider's own statement about
    what went wrong; the class name is a fallback for SDKs that wrap the
    response without exposing it.
    """

    try:
        status = status_code_of(error)

        if status is not None:
            from_status = _from_status(status)

            if from_status is not None:
                return from_status

        name = type(error).__name__

        if name in _NAMES:
            return _NAMES[name]

        for base, category in _BUILTINS:
            if isinstance(error, base):
                return category

        return ErrorCategory.INTERNAL
    except Exception:
        # A classifier that throws would turn a handled failure into an
        # unhandled one, which is precisely the rule this layer exists
        # under. Attribute access is not as safe as it looks: an SDK
        # exception can expose `status_code` as a property that raises.
        logger.exception("Failed to classify an error.")
        return ErrorCategory.INTERNAL


def describe(error: BaseException) -> dict[str, Any]:
    """
    Everything worth recording about a failure, and nothing else.

    No message, no arguments, no traceback - those are for the log, which
    is not readable through the admin API.
    """

    details: dict[str, Any] = {"error_category": classify(error).value}

    status = status_code_of(error)

    if status is not None:
        details["error_status_code"] = status

    retry_after = retry_after_of(error)

    if retry_after is not None:
        details["retry_after_seconds"] = retry_after

    return details
