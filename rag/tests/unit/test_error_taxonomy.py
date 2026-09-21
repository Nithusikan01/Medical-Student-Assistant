"""
Classifying failures.

The distinction being drawn: `error_type` names the exception class,
`error_category` says what an operator should do. A Gemini 429, a Pinecone
timeout and a malformed PDF were previously one undifferentiated bucket,
and only one of the three is fixed by waiting.

The rule the whole module rests on: classify from type and status code,
never from message text. Provider messages change without notice and
routinely echo the key the request was sent with.
"""

import pytest

from rag.observability import ErrorCategory, Stage, Tracer, classify, describe
from rag.observability.errors import retry_after_of, status_code_of


def make_error(name: str, base: type = Exception, **attributes):
    """
    An exception shaped like the SDK exception of that name.

    Built dynamically rather than importing the real thing: the SDKs are
    optional dependencies, and the classifier matches on the name anyway -
    which is the property being tested.
    """

    return _with(type(name, (base,), {})(), attributes)


def _with(error, attributes):
    for key, value in attributes.items():
        setattr(error, key, value)

    return error


class Recorder:
    def __init__(self) -> None:
        self.spans = []
        self.traces = []

    def record_span(self, span) -> None:
        self.spans.append(span)

    def record_trace(self, trace) -> None:
        self.traces.append(trace)


# ----------------------------------------------------------------------
# Status codes
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ErrorCategory.RATE_LIMIT),
        (401, ErrorCategory.AUTH),
        (403, ErrorCategory.AUTH),
        (408, ErrorCategory.TIMEOUT),
        (504, ErrorCategory.TIMEOUT),
        (400, ErrorCategory.VALIDATION),
        (422, ErrorCategory.VALIDATION),
        (500, ErrorCategory.UPSTREAM),
        (503, ErrorCategory.UPSTREAM),
    ],
)
def test_a_status_code_decides_the_category(status, expected):
    error = _with(Exception(), {"status_code": status})

    assert classify(error) == expected


def test_the_status_code_wins_over_the_class_name():
    """
    The provider's own statement about what went wrong beats our guess
    from its class name.
    """

    error = _with(make_error("InternalServerError"), {"status_code": 429})

    assert classify(error) == ErrorCategory.RATE_LIMIT


def test_a_non_http_code_attribute_is_ignored():
    """
    `code` is often an enum or an application error number. Only something
    in HTTP range is a status.
    """

    assert status_code_of(_with(Exception(), {"code": 7})) is None
    assert status_code_of(_with(Exception(), {"code": 404})) == 404


def test_a_boolean_is_not_a_status_code():
    assert status_code_of(_with(Exception(), {"status": True})) is None


# ----------------------------------------------------------------------
# Class names
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ResourceExhausted", ErrorCategory.RATE_LIMIT),
        ("RateLimitError", ErrorCategory.RATE_LIMIT),
        ("DeadlineExceeded", ErrorCategory.TIMEOUT),
        ("APITimeoutError", ErrorCategory.TIMEOUT),
        ("ServiceUnavailable", ErrorCategory.UPSTREAM),
        ("APIConnectionError", ErrorCategory.UPSTREAM),
        ("PermissionDenied", ErrorCategory.AUTH),
        ("AuthenticationError", ErrorCategory.AUTH),
        ("InvalidArgument", ErrorCategory.VALIDATION),
        ("PdfReadError", ErrorCategory.VALIDATION),
    ],
)
def test_sdk_class_names_are_recognised(name, expected):
    assert classify(make_error(name)) == expected


def test_builtin_types_are_caught_by_isinstance():
    assert classify(TimeoutError()) == ErrorCategory.TIMEOUT
    assert classify(ConnectionResetError()) == ErrorCategory.UPSTREAM


def test_an_unrecognised_failure_is_internal():
    """Our own bug, not the provider's."""

    assert classify(ValueError("something went wrong")) == ErrorCategory.INTERNAL


# ----------------------------------------------------------------------
# What is never read, and never stored
# ----------------------------------------------------------------------


def test_the_message_is_never_read():
    """
    Two exceptions of the same class, one whose message says "rate limit".
    A message-matching classifier would separate them; this must not.
    """

    quiet = ValueError("failed")
    loud = ValueError("429 rate limit exceeded for key sk-abcdef123456")

    assert classify(quiet) == classify(loud) == ErrorCategory.INTERNAL


def test_nothing_derived_from_the_message_is_returned():
    error = _with(
        make_error("RateLimitError"),
        {"status_code": 429, "retry_after": 30},
    )
    error.args = ("quota exceeded for key sk-abcdef123456",)

    details = describe(error)

    assert "sk-abcdef123456" not in str(details)
    assert details == {
        "error_category": "rate_limit",
        "error_status_code": 429,
        "retry_after_seconds": 30.0,
    }


def test_a_classifier_failure_degrades_rather_than_raising():
    """
    A classifier that throws would turn a handled failure into an
    unhandled one - the exact rule this layer exists under.
    """

    class Hostile(Exception):
        @property
        def status_code(self):
            raise RuntimeError("no")

    assert classify(Hostile()) == ErrorCategory.INTERNAL


# ----------------------------------------------------------------------
# Retry-after
# ----------------------------------------------------------------------


def test_retry_after_is_captured_when_offered():
    error = _with(make_error("RateLimitError"), {"retry_after": 45})

    assert retry_after_of(error) == 45.0


def test_a_timedelta_retry_delay_is_read():
    """google.api_core hands back a timedelta rather than a number."""

    from datetime import timedelta

    error = _with(
        make_error("ResourceExhausted"), {"retry_delay": timedelta(seconds=12)}
    )

    assert retry_after_of(error) == 12.0


def test_no_retry_after_is_none_not_zero():
    """
    Zero would read as "retry immediately", which is the opposite of what
    a rate limit with no guidance means.
    """

    assert retry_after_of(make_error("RateLimitError")) is None
    assert "retry_after_seconds" not in describe(make_error("RateLimitError"))


# ----------------------------------------------------------------------
# Through the tracer
# ----------------------------------------------------------------------


def test_a_failing_span_carries_its_category():
    recorder = Recorder()
    tracer = Tracer(recorder)

    with tracer.trace(), pytest.raises(RuntimeError), tracer.span(Stage.GENERATION):
        raise _with(
            make_error("RateLimitError", base=RuntimeError),
            {"status_code": 429},
        )

    (span,) = recorder.spans

    assert span.error_type == "RateLimitError"
    assert span.error_category == "rate_limit"
    assert span.metadata["error_status_code"] == 429


def test_the_trace_is_classified_too():
    recorder = Recorder()
    tracer = Tracer(recorder)

    with pytest.raises(TimeoutError), tracer.trace():
        raise TimeoutError()

    (trace,) = recorder.traces

    assert trace.error_category == "timeout"


def test_a_successful_span_has_no_category():
    recorder = Recorder()
    tracer = Tracer(recorder)

    with tracer.trace(), tracer.span(Stage.GENERATION):
        pass

    (span,) = recorder.spans

    assert span.error_category is None


def test_every_call_site_is_covered_without_touching_one():
    """
    Classification lives in mark_error, which every span and trace already
    passes through. A taxonomy applied by hand at each call site would be
    a taxonomy with holes in it, so this pins the single choke point.
    """

    recorder = Recorder()
    tracer = Tracer(recorder)

    stages = (Stage.RETRIEVAL, Stage.RERANKING, Stage.GENERATION)

    with tracer.trace():
        for stage in stages:
            with pytest.raises(RuntimeError), tracer.span(stage):
                raise make_error("ServiceUnavailable", base=RuntimeError)

    assert [span.error_category for span in recorder.spans] == ["upstream"] * 3
