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

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass


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


_current_trace: ContextVar[TraceContext | None] = ContextVar(
    "rag_current_trace",
    default=None,
)

_current_span_id: ContextVar[str | None] = ContextVar(
    "rag_current_span_id",
    default=None,
)


def current_trace() -> TraceContext | None:
    return _current_trace.get()


def current_trace_id() -> str | None:
    trace = _current_trace.get()

    return trace.trace_id if trace is not None else None


def current_span_id() -> str | None:
    return _current_span_id.get()


def bind_trace(trace: TraceContext | None) -> Token:
    return _current_trace.set(trace)


def reset_trace(token: Token) -> None:
    _current_trace.reset(token)


def bind_span_id(span_id: str | None) -> Token:
    return _current_span_id.set(span_id)


def reset_span_id(token: Token) -> None:
    _current_span_id.reset(token)
