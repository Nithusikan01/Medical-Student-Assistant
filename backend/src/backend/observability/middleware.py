"""
Request tracing.

A pure ASGI middleware rather than a BaseHTTPMiddleware subclass, for two
reasons that matter here: BaseHTTPMiddleware runs the downstream app in a
separate anyio task, which complicates context propagation, and it has a
history of interfering with streaming and background tasks. A plain ASGI
callable keeps the request on one task, so the trace context set here is
simply visible to everything downstream.

What it records is the trace row itself - method, route, status, duration.
It deliberately does *not* open a "request" span to go with it: that span
would carry exactly the same timing and status as its own trace row, and
section 55 of the observability spec is explicit about not storing the same
thing twice. Stage spans from the pipeline hang off the trace directly.
"""

import logging
from collections.abc import Callable

from rag.observability import Tracer, new_id
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.observability.inflight import IN_FLIGHT
from backend.wiring.rag_factory import build_tracer

logger = logging.getLogger(__name__)

TRACE_HEADER = "x-trace-id"
REQUEST_HEADER = "x-request-id"

# Where the trace handle is parked for routers and dependencies to find.
# A top-level scope key rather than `request.state`, because `scope["state"]`
# is owned by Starlette and can be replaced downstream; this one cannot.
SCOPE_KEY = "telemetry_trace"

# The load balancer health check hits this every few seconds; tracing it
# would bury real traffic in noise and grow the tables for no insight.
EXCLUDED_PATH_PREFIXES = ("/health",)

# An inbound correlation id is adopted only if it looks like one. Anything
# longer or stranger is replaced rather than stored.
MAX_REQUEST_ID_LENGTH = 64


def _clean_request_id(raw: str | None) -> str | None:
    if not raw:
        return None

    candidate = raw.strip()

    if not candidate or len(candidate) > MAX_REQUEST_ID_LENGTH:
        return None

    if not all(character.isalnum() or character in "-_=." for character in candidate):
        return None

    return candidate


def _header(scope: Scope, name: str) -> str | None:
    target = name.encode("latin-1")

    for key, value in scope.get("headers", []):
        if key == target:
            return value.decode("latin-1", errors="replace")

    return None


class TelemetryMiddleware:
    """
    Opens one trace per HTTP request and echoes its id back to the caller.

    The tracer is resolved per request from `app.state`, falling back to the
    factory, so a test can install a recording tracer the same way it
    overrides the RAG service.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        tracer_factory: Callable[[], Tracer] | None = None,
    ) -> None:
        self.app = app

        # Resolved at call time rather than bound as a default argument, so
        # the module-level factory stays patchable in tests.
        self._tracer_factory = tracer_factory

    def _tracer(self, scope: Scope) -> Tracer:
        application = scope.get("app")

        tracer = getattr(getattr(application, "state", None), "tracer", None)

        if tracer is not None:
            return tracer

        factory = self._tracer_factory or build_tracer

        return factory()

    def _should_trace(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False

        # CORS preflight never reaches a route; tracing it records nothing
        # about the application's behaviour.
        if scope.get("method") == "OPTIONS":
            return False

        path = scope.get("path", "")

        return not path.startswith(EXCLUDED_PATH_PREFIXES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_trace(scope):
            await self.app(scope, receive, send)
            return

        try:
            tracer = self._tracer(scope)
            request_id = _clean_request_id(_header(scope, REQUEST_HEADER)) or new_id()
        except Exception:
            # Telemetry could not even be set up; serve the request anyway.
            logger.exception("Could not start request tracing.")
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        IN_FLIGHT.enter()

        try:
            await self._traced(tracer, scope, receive, send, request_id, method, path)
        finally:
            IN_FLIGHT.leave()

    async def _traced(
        self,
        tracer: Tracer,
        scope: Scope,
        receive: Receive,
        send: Send,
        request_id: str,
        method: str,
        path: str,
    ) -> None:
        with tracer.trace(
            request_id=request_id,
            method=method,
            path=path,
        ) as trace:
            trace_id = trace.trace_id or request_id

            scope[SCOPE_KEY] = trace

            async def send_with_headers(message: Message) -> None:
                if message["type"] == "http.response.start":
                    try:
                        trace.set(status_code=message["status"])

                        headers = MutableHeaders(scope=message)
                        headers.append("X-Trace-ID", trace_id)
                        headers.append("X-Request-ID", request_id)
                    except Exception:
                        logger.exception("Could not annotate the response.")

                await send(message)

            await self.app(scope, receive, send_with_headers)

            # Set after routing, so this is the route template
            # ("/api/conversations/{conversation_id}") rather than the
            # concrete path - low cardinality, and it aggregates.
            try:
                route = scope.get("route")

                if route is not None:
                    trace.set(route=getattr(route, "path", None))
            except Exception:
                logger.exception("Could not record the matched route.")
