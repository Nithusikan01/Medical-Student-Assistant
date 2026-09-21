"""
How many requests are being served right now.

The one operational metric in section 15 that cannot come from the
telemetry tables: a trace row is written when a request *finishes*, so
nothing in the database knows about requests still in progress.

Two honest limitations, both of which the dashboard has to state rather
than paper over:

- it is per process, so with more than one ECS task the number is that
  task's share, not the service's total;
- it is lost on restart, which is correct - nothing is in flight then.
"""

import threading


class InFlightGauge:
    """A counter incremented for the life of each request."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current = 0
        self._peak = 0

    def enter(self) -> None:
        with self._lock:
            self._current += 1
            self._peak = max(self._peak, self._current)

    def leave(self) -> None:
        with self._lock:
            # Floored rather than allowed to go negative: an unbalanced
            # leave() would otherwise poison the gauge for the life of the
            # process.
            self._current = max(self._current - 1, 0)

    @property
    def current(self) -> int:
        return self._current

    @property
    def peak(self) -> int:
        return self._peak

    def reset_peak(self) -> None:
        with self._lock:
            self._peak = self._current


# Process-wide, because the middleware that feeds it is constructed per
# application and the value has to outlive any one request.
IN_FLIGHT = InFlightGauge()
