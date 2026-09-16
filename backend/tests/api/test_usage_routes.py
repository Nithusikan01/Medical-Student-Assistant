"""
Admin token-usage dashboard: GET /api/usage/models.

Route-level admin protection is covered generically by
test_route_protection.py; this covers the aggregation itself - that a fresh
install reports zero usage for every catalog model, that a recorded query
shows up in the right model's totals, and that usage for one model never
leaks into another's.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from rag.llm.schemas import TokenUsage

from backend.db.models import GenerationUsageEvent


def test_usage_lists_every_catalog_model_with_zero_usage_by_default(
    client: TestClient, admin, auth_headers, generation_model_ids
):
    response = client.get("/api/usage/models", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()

    ids = {row["id"] for row in body["models"]}
    assert ids == set(generation_model_ids)

    for row in body["models"]:
        assert row["daily_tokens_used"] == 0
        assert row["monthly_tokens_used"] == 0
        # Neither stub model has a configured limit (nothing in
        # rag_factory's _DAILY_TOKEN_LIMITS matches the stub ids).
        assert row["daily_token_limit"] is None
        assert row["monthly_token_limit"] is None


def test_a_query_call_is_reflected_in_that_models_usage(
    client: TestClient, user, auth_headers, admin, rag_service, generation_model_ids
):
    default_id, _ = generation_model_ids
    rag_service.usage = TokenUsage(
        prompt_tokens=100, completion_tokens=40, total_tokens=140
    )

    query_response = client.post(
        "/api/query",
        headers=auth_headers(user),
        json={
            "conversation_id": "00000000-0000-0000-0000-000000000001",
            "question": "What is the dose?",
        },
    )
    assert query_response.status_code == 200

    usage_response = client.get("/api/usage/models", headers=auth_headers(admin))
    body = usage_response.json()

    row = next(r for r in body["models"] if r["id"] == default_id)
    assert row["daily_tokens_used"] == 140
    assert row["monthly_tokens_used"] == 140

    other = next(r for r in body["models"] if r["id"] != default_id)
    assert other["daily_tokens_used"] == 0


def test_usage_outside_the_current_day_is_excluded_from_the_daily_total(
    client: TestClient, admin, auth_headers, db, generation_model_ids
):
    default_id, _ = generation_model_ids

    db.add(
        GenerationUsageEvent(
            model_id=default_id,
            provider="stub",
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
    )
    db.commit()

    response = client.get("/api/usage/models", headers=auth_headers(admin))
    row = next(r for r in response.json()["models"] if r["id"] == default_id)

    assert row["daily_tokens_used"] == 0
    # Still within this calendar month, so it counts toward the monthly total.
    assert row["monthly_tokens_used"] == 60
