"""
The monitoring API.

Goes through the real app, so these cover what the unit tests of the metric
layer cannot: window parsing, the admin gate, pagination, and that the
shapes a dashboard will bind to are actually what comes back.

Two conventions are asserted repeatedly on purpose, because collapsing
either would put a wrong number in front of someone: null is not zero, and
nothing here claims an answer was good.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.db.models import GenerationUsageEvent, ModelPricing, RagSpan, RagTrace


def add_trace(
    db,
    *,
    trace_id: str | None = None,
    minutes_ago: float = 5.0,
    duration_ms: float = 100.0,
    status: str = "ok",
    status_code: int | None = 200,
    route: str = "/api/query",
    conversation_id: uuid.UUID | None = None,
) -> str:
    trace_id = trace_id or uuid.uuid4().hex
    started = datetime.now(UTC) - timedelta(minutes=minutes_ago)

    db.add(
        RagTrace(
            id=trace_id,
            status=status,
            status_code=status_code,
            route=route,
            conversation_id=conversation_id,
            environment="test",
            app_version="test",
            started_at=started,
            ended_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
        )
    )
    db.commit()

    return trace_id


def add_span(
    db,
    *,
    trace_id: str,
    stage: str,
    sequence: int = 1,
    duration_ms: float = 50.0,
    status: str = "ok",
    error_type: str | None = None,
    meta: dict | None = None,
) -> None:
    started = datetime.now(UTC) - timedelta(minutes=5)

    db.add(
        RagSpan(
            id=uuid.uuid4().hex,
            trace_id=trace_id,
            stage=stage,
            sequence=sequence,
            status=status,
            error_type=error_type,
            started_at=started,
            ended_at=started + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
            meta=meta or {},
        )
    )
    db.commit()


def add_usage(
    db,
    *,
    trace_id: str | None = None,
    stage: str = "generation",
    model_id: str = "gemini-flash",
    prompt: int = 100,
    completion: int = 20,
    cost: str | None = None,
) -> None:
    db.add(
        GenerationUsageEvent(
            model_id=model_id,
            provider="gemini",
            stage=stage,
            trace_id=trace_id,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            estimated_cost_usd=Decimal(cost) if cost is not None else None,
        )
    )
    db.commit()


@pytest.fixture
def headers(admin, auth_headers):
    return auth_headers(admin)


# ----------------------------------------------------------------------
# Window resolution
# ----------------------------------------------------------------------


def test_the_default_window_is_a_day(client, headers):
    body = client.get("/api/monitoring/overview", headers=headers).json()

    span = datetime.fromisoformat(body["window"]["end"]) - datetime.fromisoformat(
        body["window"]["start"]
    )

    assert span == timedelta(hours=24)


def test_every_named_range_is_accepted(client, headers):
    for name in ("15m", "1h", "6h", "24h", "7d", "30d"):
        response = client.get(f"/api/monitoring/overview?range={name}", headers=headers)

        assert response.status_code == 200, name


def test_an_unknown_range_is_rejected_with_the_options(client, headers):
    response = client.get("/api/monitoring/overview?range=7years", headers=headers)

    assert response.status_code == 400
    assert "15m" in response.json()["detail"]


def test_an_explicit_window_overrides_the_named_range(client, headers):
    start = "2026-09-01T00:00:00Z"
    end = "2026-09-02T00:00:00Z"

    body = client.get(
        f"/api/monitoring/overview?start={start}&end={end}", headers=headers
    ).json()

    assert body["window"]["start"].startswith("2026-09-01")
    assert body["window"]["end"].startswith("2026-09-02")


def test_a_backwards_window_is_rejected(client, headers):
    response = client.get(
        "/api/monitoring/overview?start=2026-09-02T00:00:00Z&end=2026-09-01T00:00:00Z",
        headers=headers,
    )

    assert response.status_code == 400


def test_the_bucket_size_is_reported_so_a_chart_can_label_itself(client, headers):
    body = client.get("/api/monitoring/overview?range=1h", headers=headers).json()

    assert body["window"]["bucket_seconds"] == 60


# ----------------------------------------------------------------------
# Overview
# ----------------------------------------------------------------------


def test_an_empty_overview_reports_nothing_rather_than_zeroes(client, headers):
    body = client.get("/api/monitoring/overview", headers=headers).json()

    assert body["requests"]["total"] == 0

    # Absent, not 0.0 - "nothing happened" must not render as "instant".
    assert body["requests"]["latency"]["p95_ms"] is None
    assert body["estimated_cost_usd"] is None
    assert body["pricing_configured"] is False


def test_the_overview_counts_requests_and_tokens(client, headers, db):
    add_trace(db)
    add_trace(db, status_code=502)
    add_usage(db, prompt=1000, completion=100)

    body = client.get("/api/monitoring/overview", headers=headers).json()

    assert body["requests"]["total"] == 2
    assert body["requests"]["failed"] == 1
    assert body["total_tokens"] == 1100


def test_in_flight_is_reported_as_per_process(client, headers):
    body = client.get("/api/monitoring/overview", headers=headers).json()

    # It cannot come from the database, and the client must say so rather
    # than present it as a service-wide number.
    assert body["in_flight"]["per_process"] is True


# ----------------------------------------------------------------------
# Performance
# ----------------------------------------------------------------------


def test_performance_returns_a_series_covering_the_window(client, headers, db):
    add_trace(db)

    body = client.get("/api/monitoring/performance?range=1h", headers=headers).json()

    # 1h at 60s buckets.
    assert len(body["series"]) == 60
    assert sum(point["total"] for point in body["series"]) == 1


def test_performance_lists_stages_slowest_first(client, headers, db):
    trace_id = add_trace(db)
    add_span(db, trace_id=trace_id, stage="fusion", duration_ms=1.0)
    add_span(db, trace_id=trace_id, stage="generation", duration_ms=2000.0)

    body = client.get("/api/monitoring/performance", headers=headers).json()

    assert [stage["stage"] for stage in body["stages"]] == ["generation", "fusion"]


def test_performance_can_be_narrowed_to_one_route(client, headers, db):
    add_trace(db, route="/api/query")
    add_trace(db, route="/api/conversations")

    body = client.get(
        "/api/monitoring/performance?route=/api/query", headers=headers
    ).json()

    assert body["requests"]["total"] == 1


# ----------------------------------------------------------------------
# Tokens and cost
# ----------------------------------------------------------------------


def test_tokens_break_down_by_model_and_stage(client, headers, db):
    add_usage(db, stage="generation", prompt=1000, completion=100)
    add_usage(db, stage="query_rewrite", prompt=100, completion=10)

    body = client.get("/api/monitoring/tokens", headers=headers).json()

    assert body["total_tokens"] == 1210
    assert body["prompt_tokens"] == 1100

    stages = {row["stage"]: row["total_tokens"] for row in body["by_stage"]}

    # The correction phase 6 made: rewriting is counted too.
    assert stages == {"generation": 1100, "query_rewrite": 110}


def test_unpriced_usage_reports_null_cost_not_zero(client, headers, db):
    add_usage(db, cost=None)

    body = client.get("/api/monitoring/tokens", headers=headers).json()

    assert body["total_tokens"] > 0
    assert body["estimated_cost_usd"] is None
    assert body["pricing_configured"] is False
    assert body["by_model"][0]["estimated_cost_usd"] is None


def test_priced_usage_reports_a_cost(client, headers, db):
    add_usage(db, cost="0.000120")

    body = client.get("/api/monitoring/tokens", headers=headers).json()

    assert Decimal(body["estimated_cost_usd"]) == Decimal("0.000120")
    assert body["pricing_configured"] is True


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------


def test_retrieval_reports_an_empty_retriever(client, headers, db):
    trace_id = add_trace(db)
    add_span(
        db,
        trace_id=trace_id,
        stage="bm25_retrieval",
        meta={"result_count": 0},
    )

    body = client.get("/api/monitoring/retrieval", headers=headers).json()

    assert body["retrievers"][0]["empty_rate"] == 1.0


def test_retrieval_states_that_offline_metrics_are_not_available(client, headers):
    """
    Said plainly in the payload rather than left for a client to infer from
    absence - Recall@K and friends need ground truth this endpoint has none
    of.
    """

    body = client.get("/api/monitoring/retrieval", headers=headers).json()

    assert body["offline_metrics_available"] is False
    assert "Recall@K" in body["offline_metrics_note"]


def test_a_stage_that_did_not_run_is_null_rather_than_empty(client, headers):
    body = client.get("/api/monitoring/retrieval", headers=headers).json()

    assert body["fusion"] is None
    assert body["reranking"] is None


def test_reranking_reports_promotion_depth(client, headers, db):
    trace_id = add_trace(db)
    add_span(
        db,
        trace_id=trace_id,
        stage="reranking",
        meta={"max_promoted_rank": 16, "unused_candidate_depth": 14},
    )

    body = client.get("/api/monitoring/retrieval", headers=headers).json()

    assert body["reranking"]["max_promoted_rank"]["mean"] == 16.0
    assert body["reranking"]["unused_candidate_depth"]["mean"] == 14.0


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


def test_errors_group_by_stage_and_type(client, headers, db):
    trace_id = add_trace(db, status_code=502)
    add_span(
        db,
        trace_id=trace_id,
        stage="generation",
        status="error",
        error_type="Timeout",
    )

    body = client.get("/api/monitoring/errors", headers=headers).json()

    assert body["failed_requests"] == 1
    assert body["by_stage"][0] == {
        "stage": "generation",
        "error_type": "Timeout",
        "count": 1,
    }


# ----------------------------------------------------------------------
# Traces
# ----------------------------------------------------------------------


def test_traces_come_back_newest_first(client, headers, db):
    add_trace(db, trace_id="older", minutes_ago=30)
    add_trace(db, trace_id="newer", minutes_ago=1)

    body = client.get("/api/monitoring/traces", headers=headers).json()

    assert [t["trace_id"] for t in body["traces"]] == ["newer", "older"]


def test_a_full_page_offers_a_cursor_and_a_short_page_does_not(client, headers, db):
    for index in range(3):
        add_trace(db, minutes_ago=index + 1)

    full = client.get("/api/monitoring/traces?limit=2", headers=headers).json()
    short = client.get("/api/monitoring/traces?limit=50", headers=headers).json()

    assert len(full["traces"]) == 2
    assert full["next_before"] is not None

    # A short page is the last one; offering a cursor would send the client
    # on a pointless round trip.
    assert short["next_before"] is None


def test_the_cursor_pages_without_repeating(client, headers, db):
    for index in range(4):
        add_trace(db, trace_id=f"t{index}", minutes_ago=index + 1)

    first = client.get("/api/monitoring/traces?limit=2", headers=headers).json()
    second = client.get(
        f"/api/monitoring/traces?limit=2&before={first['next_before']}",
        headers=headers,
    ).json()

    seen = [t["trace_id"] for t in first["traces"]] + [
        t["trace_id"] for t in second["traces"]
    ]

    assert seen == ["t0", "t1", "t2", "t3"]
    assert len(set(seen)) == 4


def test_traces_can_be_filtered_to_failures(client, headers, db):
    add_trace(db, trace_id="ok", status_code=200)
    add_trace(db, trace_id="handled-502", status_code=502)
    add_trace(db, trace_id="crashed", status="error", status_code=None)

    body = client.get("/api/monitoring/traces?failed_only=true", headers=headers).json()

    # The handled 502 is the subtle one: its trace status is still "ok".
    assert {t["trace_id"] for t in body["traces"]} == {"handled-502", "crashed"}


def test_traces_can_be_filtered_to_one_conversation(client, headers, db):
    conversation_id = uuid.uuid4()

    add_trace(db, trace_id="mine", conversation_id=conversation_id)
    add_trace(db, trace_id="other", conversation_id=uuid.uuid4())

    body = client.get(
        f"/api/monitoring/traces?conversation_id={conversation_id}", headers=headers
    ).json()

    assert [t["trace_id"] for t in body["traces"]] == ["mine"]


def test_an_oversized_page_is_rejected(client, headers):
    assert (
        client.get("/api/monitoring/traces?limit=5000", headers=headers).status_code
        == 422
    )


# ----------------------------------------------------------------------
# One trace, end to end
# ----------------------------------------------------------------------


def test_a_trace_detail_returns_its_waterfall_in_order(client, headers, db):
    trace_id = add_trace(db)

    # Inserted out of order on purpose: sequence is what orders them, not
    # insertion and not started_at.
    add_span(db, trace_id=trace_id, stage="generation", sequence=3)
    add_span(db, trace_id=trace_id, stage="memory_load", sequence=1)
    add_span(db, trace_id=trace_id, stage="retrieval", sequence=2)

    body = client.get(f"/api/monitoring/traces/{trace_id}", headers=headers).json()

    assert [span["stage"] for span in body["spans"]] == [
        "memory_load",
        "retrieval",
        "generation",
    ]


def test_a_trace_detail_includes_every_llm_call(client, headers, db):
    trace_id = add_trace(db)

    add_usage(db, trace_id=trace_id, stage="query_rewrite", prompt=139, completion=11)
    add_usage(db, trace_id=trace_id, stage="generation", prompt=1171, completion=120)

    body = client.get(f"/api/monitoring/traces/{trace_id}", headers=headers).json()

    assert {token["stage"] for token in body["tokens"]} == {
        "query_rewrite",
        "generation",
    }

    # 150 + 1291: the total a request really cost, not just its answer.
    assert body["total_tokens"] == 1441


def test_span_metadata_survives_to_the_client(client, headers, db):
    """The trace explorer renders scores and counts straight from this."""

    trace_id = add_trace(db)
    add_span(
        db,
        trace_id=trace_id,
        stage="dense_retrieval",
        meta={"result_count": 30, "top_score": 0.91},
    )

    body = client.get(f"/api/monitoring/traces/{trace_id}", headers=headers).json()

    assert body["spans"][0]["metadata"]["result_count"] == 30
    assert body["spans"][0]["metadata"]["top_score"] == 0.91


def test_an_unknown_trace_is_a_404(client, headers):
    assert client.get("/api/monitoring/traces/nope", headers=headers).status_code == 404


# ----------------------------------------------------------------------
# Access
# ----------------------------------------------------------------------


def test_a_non_admin_cannot_read_monitoring(client, user, auth_headers):
    """
    Monitoring exposes every user's traffic, conversation ids and spend.
    There is no per-user view of it.
    """

    for path in (
        "/api/monitoring/overview",
        "/api/monitoring/tokens",
        "/api/monitoring/traces",
    ):
        assert client.get(path, headers=auth_headers(user)).status_code == 403


def test_an_anonymous_request_is_rejected(client):
    assert client.get("/api/monitoring/overview").status_code == 401


def test_pricing_rows_are_not_exposed(client, headers, db):
    """
    The pricing table is configuration, not telemetry; the monitoring API
    reports what things cost, never the rate card itself.
    """

    db.add(
        ModelPricing(
            model_id="gemini-flash",
            provider="gemini",
            input_cost_per_1m_usd=Decimal("0.10"),
            output_cost_per_1m_usd=Decimal("0.40"),
            effective_from=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db.commit()

    body = client.get("/api/monitoring/tokens", headers=headers).json()

    assert "input_cost_per_1m_usd" not in str(body)
