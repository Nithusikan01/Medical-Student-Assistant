"""
Ambient trace context.

Contextvars rather than threading a trace_id through every signature: the
engine's components would otherwise all need a new parameter, which is the
kind of invasive change section 3 of the spec rules out. FastAPI copies the
context into the worker thread it runs synchronous endpoints on, so this
survives the `def` (not `async def`) routes this application uses.

Nothing here is imported by the rest of the engine except the tracer, so a
caller that wants explicit propagation can still pass a Tracer around.
"""

import itertools
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


def new_id() -> str:
    """
    A 32-character hex id.

    Deliberately the shape of an OpenTelemetry trace id rather than a dashed
    UUID, so these records can be handed to an OTel exporter later without
    re-keying anything (spec section 49).
    """

    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class TraceContext:
    """The trace the current unit of work belongs to."""

    trace_id: str

    request_id: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None

    # False when sampling excluded this trace. Spans check it, so an
    # unsampled request costs one random() call and nothing else.
    sampled: bool = True

    # Hands out a monotonic position to each span in this trace.
    #
    # Ordering a waterfall by started_at does not work: the wall clock is
    # coarser than the gap between a parent span and the child it opens, so
    # retrieval, dense_retrieval and query_embedding routinely share one
    # timestamp to the microsecond and render scrambled. itertools.count is
    # not thread-safe in general, but next() on it is a single bytecode step
    # under CPython, and a trace is in any case confined to one request.
    sequence: Any = field(default_factory=lambda: itertools.count(1))


_current_trace: ContextVar[TraceContext | None] = ContextVar(
    "rag_current_trace",
    default=None,
)

# Holds the in-flight SpanHandle, not just its id, so a component nested
# inside someone else's span can annotate it - FallbackReranker recording
# which reranker actually answered, for instance - without opening a second
# span that would duplicate the first one's timing. Typed loosely because
# the handle lives in tracer.py, which imports this module.
_current_span: ContextVar[Any | None] = ContextVar(
    "rag_current_span",
    default=None,
)

# The stage name of the innermost open span, bound whether or not the trace
# is being recorded. Token metering attributes spend by stage, and billing
# must not change depending on whether a request happened to be sampled.
_current_stage: ContextVar[str | None] = ContextVar(
    "rag_current_stage",
    default=None,
)


def current_trace() -> TraceContext | None:
    return _current_trace.get()


def current_trace_id() -> str | None:
    trace = _current_trace.get()

    return trace.trace_id if trace is not None else None


def current_span() -> Any | None:
    return _current_span.get()


def current_span_id() -> str | None:
    span = _current_span.get()

    return getattr(span, "span_id", None) if span is not None else None


def bind_trace(trace: TraceContext | None) -> Token:
    return _current_trace.set(trace)


def reset_trace(token: Token) -> None:
    _current_trace.reset(token)


def bind_span(span: Any | None) -> Token:
    return _current_span.set(span)


def reset_span(token: Token) -> None:
    _current_span.reset(token)


def current_stage() -> str | None:
    return _current_stage.get()


def bind_stage(stage: str | None) -> Token:
    return _current_stage.set(stage)


def reset_stage(token: Token) -> None:
    _current_stage.reset(token)


def next_sequence(trace: TraceContext | None) -> int:
    """The next span position within a trace, or 0 outside one."""

    if trace is None or trace.sequence is None:
        return 0

    try:
        return next(trace.sequence)
    except (TypeError, StopIteration):
        # TypeError if something other than a counter ended up in the field;
        # StopIteration is unreachable for itertools.count but costs nothing
        # to guard. Either way an unnumbered span beats a failed request.
        return 0
