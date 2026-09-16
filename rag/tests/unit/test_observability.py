"""
The tracer's contract.

The important tests here are the negative ones: a broken recorder, a
metadata value that cannot be handled, and an unsampled trace all have to
leave the wrapped code working. That is the whole point of the design - a
monitoring failure must never become a RAG failure.
"""

import pytest

from rag.observability import (
    SpanRecord,
    SpanStatus,
    Stage,
    Tracer,
    TraceRecord,
    current_trace,
    sanitize_metadata,
)
from rag.observability.sanitize import MAX_STRING_LENGTH, REDACTED


class RecordingRecorder:
    """Collects everything, so tests can assert on the emitted records."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self.traces: list[TraceRecord] = []

    def record_span(self, span: SpanRecord) -> None:
        self.spans.append(span)

    def record_trace(self, trace: TraceRecord) -> None:
        self.traces.append(trace)


class BrokenRecorder:
    """Fails on every call, the way a wedged telemetry backend would."""

    def record_span(self, span: SpanRecord) -> None:
        raise RuntimeError("recorder is down")

    def record_trace(self, trace: TraceRecord) -> None:
        raise RuntimeError("recorder is down")


@pytest.fixture
def recorder() -> RecordingRecorder:
    return RecordingRecorder()


@pytest.fixture
def tracer(recorder: RecordingRecorder) -> Tracer:
    return Tracer(recorder, environment="test", app_version="0.0.0-test")


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------


def test_trace_records_one_row_with_its_identifiers(tracer, recorder):
    with tracer.trace(request_id="req-1", conversation_id="conv-1", user_id="user-1"):
        pass

    assert len(recorder.traces) == 1

    trace = recorder.traces[0]

    assert trace.request_id == "req-1"
    assert trace.conversation_id == "conv-1"
    assert trace.user_id == "user-1"
    assert trace.status is SpanStatus.OK
    assert trace.environment == "test"
    assert trace.app_version == "0.0.0-test"
    assert trace.duration_ms >= 0.0


def test_spans_nest_under_their_parent(tracer, recorder):
    with tracer.trace(), tracer.span(Stage.RETRIEVAL):
        with tracer.span(Stage.DENSE_RETRIEVAL):
            pass

        with tracer.span(Stage.BM25_RETRIEVAL):
            pass

    stages = {span.stage: span for span in recorder.spans}

    assert set(stages) == {"retrieval", "dense_retrieval", "bm25_retrieval"}

    parent = stages["retrieval"]

    assert parent.parent_span_id is None
    assert stages["dense_retrieval"].parent_span_id == parent.span_id
    assert stages["bm25_retrieval"].parent_span_id == parent.span_id

    # Every span belongs to the same trace as its parent.
    assert {span.trace_id for span in recorder.spans} == {parent.trace_id}


def test_span_metadata_is_attached(tracer, recorder):
    with tracer.trace(), tracer.span(Stage.RERANKING, reranker="pinecone") as span:
        span.set(candidate_count=30, final_count=5)

    assert recorder.spans[0].metadata == {
        "reranker": "pinecone",
        "candidate_count": 30,
        "final_count": 5,
    }


def test_trace_id_is_adopted_when_supplied(tracer, recorder):
    with tracer.trace(trace_id="abc123") as trace:
        assert trace.trace_id == "abc123"

    assert recorder.traces[0].trace_id == "abc123"


def test_conversation_can_be_attached_after_the_trace_starts(tracer, recorder):
    with tracer.trace() as trace:
        trace.set_conversation("conv-9")

    assert recorder.traces[0].conversation_id == "conv-9"


# ----------------------------------------------------------------------
# Errors in the traced code
# ----------------------------------------------------------------------


def test_span_records_the_error_and_re_raises(tracer, recorder):
    with pytest.raises(ValueError), tracer.trace(), tracer.span(Stage.GENERATION):
        raise ValueError("the model said no")

    span = recorder.spans[0]

    assert span.status is SpanStatus.ERROR
    assert span.error_type == "ValueError"

    # The failure propagates to the trace as well.
    assert recorder.traces[0].status is SpanStatus.ERROR
    assert recorder.traces[0].error_type == "ValueError"


# ----------------------------------------------------------------------
# Telemetry failures must not surface
# ----------------------------------------------------------------------


def test_a_broken_recorder_does_not_break_the_traced_code():
    tracer = Tracer(BrokenRecorder())

    calls = []

    with tracer.trace(), tracer.span(Stage.GENERATION):
        calls.append("work happened")

    assert calls == ["work happened"]


def test_a_broken_recorder_still_lets_an_application_error_through():
    tracer = Tracer(BrokenRecorder())

    with pytest.raises(ValueError), tracer.trace(), tracer.span(Stage.GENERATION):
        raise ValueError("real failure")


def test_span_outside_a_trace_records_nothing(tracer, recorder):
    with tracer.span(Stage.GENERATION) as span:
        span.set(anything=1)

    assert recorder.spans == []
    assert span.recording is False


def test_unsampled_trace_records_nothing_but_still_has_an_id(recorder):
    tracer = Tracer(recorder, sample_rate=0.0)

    with tracer.trace() as trace:
        with tracer.span(Stage.GENERATION):
            pass

        assert trace.trace_id is not None

    assert recorder.traces == []
    assert recorder.spans == []


def test_context_is_cleared_when_the_trace_exits(tracer):
    with tracer.trace():
        assert current_trace() is not None

    assert current_trace() is None


def test_context_is_cleared_even_when_the_body_raises(tracer):
    with pytest.raises(RuntimeError), tracer.trace():
        raise RuntimeError("boom")

    assert current_trace() is None


def test_default_tracer_is_a_working_no_op():
    """A Tracer with no recorder is what the engine uses by default."""

    tracer = Tracer()

    with tracer.trace(), tracer.span(Stage.QUERY_REWRITE) as span:
        span.set(rewritten_length=12)


# ----------------------------------------------------------------------
# Sanitisation
# ----------------------------------------------------------------------


def test_sensitive_keys_are_redacted():
    cleaned = sanitize_metadata(
        {
            "api_key": "pcsk_real_key",
            "PINECONE_API_KEY": "pcsk_real_key",
            "access_token": "ey...",
            "password": "hunter2",
            "model": "gemini-3.1-flash-lite",
        }
    )

    assert cleaned["api_key"] == REDACTED
    assert cleaned["PINECONE_API_KEY"] == REDACTED
    assert cleaned["access_token"] == REDACTED
    assert cleaned["password"] == REDACTED
    assert cleaned["model"] == "gemini-3.1-flash-lite"


def test_token_counts_are_not_mistaken_for_credentials():
    """
    A bare "token" substring match redacted `prompt_tokens` and
    `total_tokens`, which would have made token accounting - the one thing
    this application already monitored - impossible to record.
    """

    cleaned = sanitize_metadata(
        {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "max_output_tokens": 1024,
        }
    )

    assert cleaned == {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
        "max_output_tokens": 1024,
    }


def test_singular_credential_names_are_still_caught():
    cleaned = sanitize_metadata(
        {
            "user_token": "leaked",
            "gemini_key": "leaked",
            "token": "leaked",
            "key": "leaked",
            "session": "leaked",
        }
    )

    assert set(cleaned.values()) == {REDACTED}


def test_long_strings_are_truncated():
    cleaned = sanitize_metadata({"note": "x" * 5000})

    assert len(cleaned["note"]) < 5000
    assert cleaned["note"].startswith("x" * MAX_STRING_LENGTH)


def test_nested_structures_are_sanitised():
    cleaned = sanitize_metadata(
        {
            "config": {"api_key": "secret", "top_k": 5},
            "scores": [0.9, 0.8, 0.7],
        }
    )

    assert cleaned["config"]["api_key"] == REDACTED
    assert cleaned["config"]["top_k"] == 5
    assert cleaned["scores"] == [0.9, 0.8, 0.7]


def test_sanitised_metadata_reaches_the_recorder(tracer, recorder):
    with tracer.trace(), tracer.span(Stage.DENSE_RETRIEVAL) as span:
        span.set(api_key="pcsk_leaked", result_count=20)

    assert recorder.spans[0].metadata == {
        "api_key": REDACTED,
        "result_count": 20,
    }


def test_unrepresentable_values_do_not_break_a_span(tracer, recorder):
    class Awkward:
        def __repr__(self) -> str:
            raise RuntimeError("cannot be shown")

    with tracer.trace(), tracer.span(Stage.GENERATION) as span:
        span.set(thing=Awkward())

    # The span is still recorded; only its metadata is sacrificed.
    assert len(recorder.spans) == 1
    assert recorder.spans[0].metadata == {}
