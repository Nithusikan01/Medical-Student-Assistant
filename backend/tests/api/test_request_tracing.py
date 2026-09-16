"""
Request tracing through the real middleware stack.

These run against the actual application, so they cover the thing unit
tests cannot: that the middleware is installed in the right order, that the
trace reaches routers through the request scope, and that a failing tracer
still leaves the API answering.
"""

import uuid

import pytest
from rag.observability import SpanRecord, SpanStatus, Tracer, TraceRecord


class RecordingRecorder:
    def __init__(self) -> None:
        self.traces: list[TraceRecord] = []
        self.spans: list[SpanRecord] = []

    def record_span(self, span: SpanRecord) -> None:
        self.spans.append(span)

    def record_trace(self, trace: TraceRecord) -> None:
        self.traces.append(trace)


@pytest.fixture
def recorder() -> RecordingRecorder:
    return RecordingRecorder()


@pytest.fixture
def traced_client(client, recorder: RecordingRecorder):
    """
    The standard client, with a recording tracer installed the same way the
    lifespan installs the real one.
    """

    client.app.state.tracer = Tracer(recorder, environment="test")

    return client


# ----------------------------------------------------------------------
# Correlation headers
# ----------------------------------------------------------------------


def test_every_response_carries_a_trace_and_request_id(
    traced_client, user, auth_headers
):
    response = traced_client.get("/api/conversations", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.headers["x-trace-id"]
    assert response.headers["x-request-id"]


def test_an_inbound_request_id_is_adopted(traced_client, user, auth_headers, recorder):
    response = traced_client.get(
        "/api/conversations",
        headers={**auth_headers(user), "X-Request-ID": "edge-abc-123"},
    )

    assert response.headers["x-request-id"] == "edge-abc-123"
    assert recorder.traces[0].request_id == "edge-abc-123"


def test_a_junk_request_id_is_replaced_rather_than_stored(
    traced_client,
    user,
    auth_headers,
    recorder,
):
    response = traced_client.get(
        "/api/conversations",
        headers={**auth_headers(user), "X-Request-ID": "x" * 500},
    )

    assert response.headers["x-request-id"] != "x" * 500
    assert recorder.traces[0].request_id != "x" * 500


def test_the_response_id_matches_the_recorded_trace(
    traced_client,
    user,
    auth_headers,
    recorder,
):
    response = traced_client.get("/api/conversations", headers=auth_headers(user))

    assert recorder.traces[0].trace_id == response.headers["x-trace-id"]


# ----------------------------------------------------------------------
# What gets recorded
# ----------------------------------------------------------------------


def test_the_trace_records_method_route_and_status(
    traced_client,
    user,
    auth_headers,
    recorder,
):
    traced_client.get("/api/conversations", headers=auth_headers(user))

    trace = recorder.traces[0]

    assert trace.metadata["method"] == "GET"
    assert trace.metadata["status_code"] == 200

    # The route template, not the concrete path.
    assert trace.metadata["route"] == "/api/conversations"


def test_path_parameters_are_recorded_as_a_template(
    traced_client,
    user,
    auth_headers,
    recorder,
):
    conversation_id = uuid.uuid4()

    traced_client.get(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(user),
    )

    trace = recorder.traces[0]

    assert trace.metadata["route"] == "/api/conversations/{conversation_id}"
    assert trace.metadata["status_code"] == 404


def test_the_authenticated_user_is_attached(
    traced_client, user, auth_headers, recorder
):
    traced_client.get("/api/conversations", headers=auth_headers(user))

    assert recorder.traces[0].user_id == str(user.id)


def test_an_unauthenticated_request_is_still_traced(traced_client, recorder):
    response = traced_client.get("/api/conversations")

    assert response.status_code == 401
    assert recorder.traces[0].metadata["status_code"] == 401
    assert recorder.traces[0].user_id is None


def test_health_checks_are_not_traced(traced_client, recorder):
    response = traced_client.get("/health/health")

    assert response.status_code == 200
    assert recorder.traces == []

    # Nothing to correlate, so nothing is added to the response either.
    assert "x-trace-id" not in response.headers


# ----------------------------------------------------------------------
# The query route
# ----------------------------------------------------------------------


def test_query_populates_processing_time_and_conversation(
    traced_client,
    user,
    auth_headers,
    recorder,
):
    conversation_id = str(uuid.uuid4())

    response = traced_client.post(
        "/api/query",
        headers=auth_headers(user),
        json={"conversation_id": conversation_id, "question": "What is the dose?"},
    )

    assert response.status_code == 200

    # The field has been on the response model, and null, since it was
    # written; this is the first release where it means something.
    assert response.json()["processing_time_ms"] >= 0

    trace = recorder.traces[0]

    assert trace.conversation_id == conversation_id
    assert trace.user_id == str(user.id)
    assert trace.metadata["source_count"] == 0
    assert trace.metadata["processing_time_ms"] >= 0


def test_a_failing_query_is_traced_as_an_error(
    traced_client,
    user,
    auth_headers,
    recorder,
    rag_service,
):
    rag_service.error = RuntimeError("pinecone is down")

    response = traced_client.post(
        "/api/query",
        headers=auth_headers(user),
        json={"conversation_id": str(uuid.uuid4()), "question": "What is the dose?"},
    )

    assert response.status_code == 502
    assert recorder.traces[0].metadata["status_code"] == 502


def test_an_unhandled_exception_is_traced_as_an_error(traced_client, recorder):
    """
    Nothing in the API is expected to raise past its router, but if it did,
    the trace has to say so - the status header never gets written in that
    case, so the error type is the only record of what happened.
    """

    @traced_client.app.get("/api/_explode_for_test")
    def explode():
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        traced_client.get("/api/_explode_for_test")

    trace = recorder.traces[0]

    assert trace.status is SpanStatus.ERROR
    assert trace.error_type == "RuntimeError"


# ----------------------------------------------------------------------
# Regression: tracing must not be able to break a request
# ----------------------------------------------------------------------


def test_a_broken_tracer_leaves_the_api_working(client, user, auth_headers):
    class BrokenRecorder:
        def record_span(self, span):
            raise RuntimeError("recorder is down")

        def record_trace(self, trace):
            raise RuntimeError("recorder is down")

    client.app.state.tracer = Tracer(BrokenRecorder())

    response = client.get("/api/conversations", headers=auth_headers(user))

    assert response.status_code == 200


def test_a_tracer_that_cannot_be_built_leaves_the_api_working(
    client,
    user,
    auth_headers,
    monkeypatch,
):
    """
    app.state.tracer is absent until the lifespan runs, and the API tests
    deliberately never run it - so the middleware falls back to the factory.
    This pins that a factory which blows up is survivable too.
    """

    def explode():
        raise RuntimeError("no database url")

    # Drop back to the factory path the lifespan would normally fill in.
    client.app.state.tracer = None

    monkeypatch.setattr(
        "backend.observability.middleware.build_tracer",
        explode,
    )

    response = client.get("/api/conversations", headers=auth_headers(user))

    assert response.status_code == 200
