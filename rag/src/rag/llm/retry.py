"""
When a failed provider call is worth repeating, and how long to wait.

Shared by every generator so they agree: retry what a retry can fix (rate
limits, timeouts, provider outages, an empty completion) and fail fast on
what it cannot (a rejected key, an invalid request, our own bug). Retrying
everything turned a revoked API key into three slow failures.
"""

from rag.observability import is_transient, retry_after_of

# Never sleep longer than this, whatever the provider asks for: a user is
# waiting on the request.
MAX_RETRY_DELAY_SECONDS = 20.0


class EmptyResponseError(RuntimeError):
    """The provider answered but returned no text. Worth one more try."""


def should_retry(error: BaseException) -> bool:
    return isinstance(error, EmptyResponseError) or is_transient(error)


def retry_delay(error: BaseException, attempt: int, base_delay: float) -> float:
    """
    The provider's own Retry-After when it gives one, otherwise exponential
    backoff from `base_delay`. Capped either way.
    """

    requested = retry_after_of(error)

    if requested is not None:
        return min(requested, MAX_RETRY_DELAY_SECONDS)

    return min(base_delay * 2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS)
