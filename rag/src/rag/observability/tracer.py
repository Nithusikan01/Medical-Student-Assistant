"""
The tracer: how the pipeline actually emits telemetry.

Design rule, from section 9 of the observability spec:

    telemetry failure -> log it, continue the RAG request

not

    telemetry failure -> RAG request fails

Every operation in this module that could raise is guarded, and the guards
degrade to a non-recording handle rather than to an exception. A call site
can therefore write

    with tracer.span(Stage.RERANKING) as span:
        results = reranker.rerank(...)
        span.set(candidate_count=len(candidates), final_count=len(results))

and be confident that a broken recorder, a full queue, or an unserialisable
metadata value cannot turn a working answer into a 502.
"""

import logging
import random
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from rag.observability.context import (
    TraceContext,
    bind_span,
    bind_stage,
    bind_trace,
    current_span,
    current_span_id,
    current_trace,
    new_id,
    next_sequence,
    reset_span,
    reset_stage,
    reset_trace,
)
from rag.observability.protocol import TraceRecorder
from rag.observability.sanitize import sanitize_metadata
from rag.observability.schemas import (
    SpanRecord,
    SpanStatus,
    Stage,
    TraceRecord,
)

logger = logging.getLogger(__name__)


class NullRecorder:
    """
    Records nothing.

    The default, so the engine's components can hold a Tracer
    unconditionally and stay runnable with no telemetry backend wired up.
    """

    def record_span(self, span: SpanRecord) -> None:
        return None

    def record_trace(self, trace: TraceRecord) -> None:
        return None


class _Handle:
    """
    Mutable state for an in-flight trace or span.

    `recording` false makes every mutator a no-op, which is what lets this
    module share one NULL handle across all non-recording call sites instead
    of allocating a throwaway object per skipped span.
    """

    __slots__ = (
        "_error_type",
        "_metadata",
        "_start_perf",
        "_started_at",
        "_status",
        "recording",
    )

    def __init__(self, *, recording: bool) -> None:
        self.recording = recording
        self._metadata: dict[str, Any] = {}
        self._status = SpanStatus.OK
        self._error_type: str | None = None
        self._started_at = datetime.now(UTC) if recording else None
        self._start_perf = time.perf_counter() if recording else None

    def set(self, **fields: Any) -> None:
        """
        Attach metadata. Never raises, whatever is handed to it.
        """

        if not self.recording:
            return

        try:
            self._metadata.update(fields)
        except Exception:
            logger.exception("Failed to attach telemetry metadata.")

    def mark_error(self, error: BaseException) -> None:
        if not self.recording:
            return

        self._status = SpanStatus.ERROR
        self._error_type = type(error).__name__

    def _duration_ms(self) -> float:
        if self._start_perf is None:
            return 0.0

        return (time.perf_counter() - self._start_perf) * 1000.0


class SpanHandle(_Handle):
    """One stage of work, handed to the body of Tracer.span."""

    __slots__ = ("parent_span_id", "sequence", "span_id", "stage", "trace_id")

    def __init__(
        self,
        *,
        stage: str = "",
        trace_id: str = "",
        span_id: str = "",
        parent_span_id: str | None = None,
        sequence: int = 0,
        recording: bool = False,
    ) -> None:
        super().__init__(recording=recording)

        self.stage = stage
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.sequence = sequence

    def to_record(self) -> SpanRecord:
        ended_at = datetime.now(UTC)

        return SpanRecord(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            stage=self.stage,
            sequence=self.sequence,
            started_at=self._started_at or ended_at,
            ended_at=ended_at,
            duration_ms=self._duration_ms(),
            status=self._status,
            error_type=self._error_type,
            metadata=sanitize_metadata(self._metadata),
        )


class TraceHandle(_Handle):
    """One end-to-end request, handed to the body of Tracer.trace."""

    __slots__ = ("app_version", "context", "environment")

    def __init__(
        self,
        *,
        context: TraceContext | None = None,
        environment: str | None = None,
        app_version: str | None = None,
        recording: bool = False,
    ) -> None:
        super().__init__(recording=recording)

        self.context = context
        self.environment = environment
        self.app_version = app_version

    @property
    def trace_id(self) -> str | None:
        """
        The id to echo back to the client, or None when nothing started.

        Readable even for an unsampled trace - the id exists, it just has no
        stored rows.
        """

        return self.context.trace_id if self.context is not None else None

    def set_conversation(self, conversation_id: str | None) -> None:
        """
        Attach the conversation once the router knows it.

        The id is only established after the request body is parsed and
        ownership is checked, which is later than the trace has to start.
        """

        if self.context is None or conversation_id is None:
            return

        # replace() rather than a fresh TraceContext: rebuilding it field by
        # field drops the span sequence counter, silently restarting every
        # span position at 1 partway through the trace.
        self.context = replace(self.context, conversation_id=str(conversation_id))

    def set_user(self, user_id: str | None) -> None:
        """
        Attach the authenticated user once the request has been authorised.

        Like the conversation, this is known only after the trace has
        already started - authentication is a dependency, not middleware.
        """

        if self.context is None or user_id is None:
            return

        self.context = replace(self.context, user_id=str(user_id))

    def to_record(self) -> TraceRecord:
        ended_at = datetime.now(UTC)
        context = self.context

        return TraceRecord(
            trace_id=context.trace_id if context else "",
            request_id=context.request_id if context else None,
            conversation_id=context.conversation_id if context else None,
            user_id=context.user_id if context else None,
            started_at=self._started_at or ended_at,
            ended_at=ended_at,
            duration_ms=self._duration_ms(),
            status=self._status,
            error_type=self._error_type,
            environment=self.environment,
            app_version=self.app_version,
            metadata=sanitize_metadata(self._metadata),
        )


# Shared because a non-recording handle holds no state that can be mutated:
# every mutator returns early when `recording` is False.
NULL_SPAN = SpanHandle()
NULL_TRACE = TraceHandle()


class Tracer:
    """
    Creates traces and spans, and hands completed records to a recorder.

    Held by components as an ordinary collaborator. The default recorder
    records nothing, so `Tracer()` is a working no-op and existing tests
    need no telemetry setup.
    """

    def __init__(
        self,
        recorder: TraceRecorder | None = None,
        *,
        sample_rate: float = 1.0,
        environment: str | None = None,
        app_version: str | None = None,
    ) -> None:
        self._recorder: TraceRecorder = (
            recorder if recorder is not None else NullRecorder()
        )

        self._sample_rate = min(max(float(sample_rate), 0.0), 1.0)
        self._environment = environment
        self._app_version = app_version

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    @contextmanager
    def trace(
        self,
        *,
        trace_id: str | None = None,
        request_id: str | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        **metadata: Any,
    ) -> Iterator[TraceHandle]:
        """
        Open a trace for one request and bind it to the current context.

        `trace_id` is accepted so an upstream id (a load balancer's, or a
        client's) can be adopted rather than replaced.
        """

        handle = NULL_TRACE
        token = None

        try:
            sampled = self._sample_rate >= 1.0 or random.random() < self._sample_rate

            context = TraceContext(
                trace_id=trace_id or new_id(),
                request_id=request_id,
                conversation_id=str(conversation_id) if conversation_id else None,
                user_id=str(user_id) if user_id else None,
                sampled=sampled,
            )

            handle = TraceHandle(
                context=context,
                environment=self._environment,
                app_version=self._app_version,
                recording=sampled,
            )

            handle.set(**metadata)

            token = bind_trace(context)
        except Exception:
            logger.exception("Failed to start a telemetry trace.")
            handle = NULL_TRACE

        try:
            yield handle
        except BaseException as error:
            handle.mark_error(error)
            raise
        finally:
            self._close_trace(handle, token)

    def _close_trace(self, handle: TraceHandle, token: Any) -> None:
        try:
            if handle.recording:
                self._recorder.record_trace(handle.to_record())
        except Exception:
            logger.exception("Failed to record a telemetry trace.")
        finally:
            if token is not None:
                try:
                    reset_trace(token)
                except Exception:
                    logger.exception("Failed to reset the trace context.")

    # ------------------------------------------------------------------
    # Spans
    # ------------------------------------------------------------------

    @contextmanager
    def span(self, stage: Stage | str, **metadata: Any) -> Iterator[SpanHandle]:
        """
        Time one stage of work inside the current trace.

        Outside a trace, or inside an unsampled one, this yields the shared
        non-recording handle and stores nothing - so engine code can be
        instrumented unconditionally, and a script or unit test exercising
        the same code path produces no telemetry.
        """

        handle = NULL_SPAN
        token = None
        stage_token = None

        name = stage.value if isinstance(stage, Stage) else str(stage)

        try:
            # Bound whether or not this trace is recorded: token metering
            # attributes spend by stage, and what a request costs must not
            # depend on whether it happened to be sampled.
            stage_token = bind_stage(name)

            context = current_trace()

            if context is not None and context.sampled:
                handle = SpanHandle(
                    stage=name,
                    trace_id=context.trace_id,
                    span_id=new_id(),
                    parent_span_id=current_span_id(),
                    sequence=next_sequence(context),
                    recording=True,
                )

                handle.set(**metadata)

                token = bind_span(handle)
        except Exception:
            logger.exception("Failed to start a telemetry span.")
            handle = NULL_SPAN

        try:
            yield handle
        except BaseException as error:
            handle.mark_error(error)
            raise
        finally:
            self._close_span(handle, token, stage_token)

    def annotate(self, **fields: Any) -> None:
        """
        Attach metadata to the span that is currently open, if any.

        For a component that has something worth recording but no business
        opening a span of its own - FallbackReranker knows which reranker
        answered, but the reranking span belongs to QueryService, and a
        second span would duplicate its timing for no added information.

        Silently does nothing outside a span, which is what makes it safe
        to call from a component that may or may not be instrumented.
        """

        try:
            span = current_span()

            if span is not None:
                span.set(**fields)
        except Exception:
            logger.exception("Failed to annotate the current telemetry span.")

    def _close_span(self, handle: SpanHandle, token: Any, stage_token: Any) -> None:
        try:
            if handle.recording:
                self._recorder.record_span(handle.to_record())
        except Exception:
            logger.exception("Failed to record a telemetry span.")
        finally:
            for reset, active in ((reset_span, token), (reset_stage, stage_token)):
                if active is not None:
                    try:
                        reset(active)
                    except Exception:
                        logger.exception("Failed to reset the span context.")
