"""
Cost estimation and per-stage usage accounting.

The distinction these tests defend hardest is between "no price configured"
and "cost zero". They are different facts, and collapsing them puts a
confident $0.00 on a dashboard for models nobody has priced.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rag.llm.metering import UsageEvent
from rag.llm.schemas import TokenUsage

from backend.db.models import ModelPricing
from backend.db.repositories import usage as repo
from backend.services.pricing import estimate_cost, rate_for

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def add_rate(
    db,
    *,
    model_id: str = "gemini-flash",
    provider: str = "gemini",
    input_usd: str = "0.10",
    output_usd: str = "0.40",
    effective_from: datetime = NOW - timedelta(days=30),
    effective_to: datetime | None = None,
) -> ModelPricing:
    row = ModelPricing(
        model_id=model_id,
        provider=provider,
        input_cost_per_1m_usd=Decimal(input_usd),
        output_cost_per_1m_usd=Decimal(output_usd),
        effective_from=effective_from,
        effective_to=effective_to,
    )

    db.add(row)
    db.commit()

    return row


def usage_of(prompt: int = 1_000_000, completion: int = 0) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


# ----------------------------------------------------------------------
# Rate lookup
# ----------------------------------------------------------------------


def test_the_rate_in_effect_is_found(db):
    add_rate(db)

    rate = rate_for(db, model_id="gemini-flash", at=NOW)

    assert rate is not None
    assert Decimal(rate.input_cost_per_1m_usd) == Decimal("0.10")


def test_a_model_with_no_rate_returns_none(db):
    assert rate_for(db, model_id="never-priced", at=NOW) is None


def test_a_superseded_rate_is_not_used(db):
    add_rate(
        db,
        input_usd="1.00",
        effective_from=NOW - timedelta(days=60),
        effective_to=NOW - timedelta(days=10),
    )
    add_rate(db, input_usd="0.10", effective_from=NOW - timedelta(days=10))

    rate = rate_for(db, model_id="gemini-flash", at=NOW)

    assert Decimal(rate.input_cost_per_1m_usd) == Decimal("0.10")


def test_a_historical_cost_uses_the_rate_of_its_time(db):
    """
    Prices are time-bounded rather than mutated, so what a call cost stays
    explicable after a price change instead of silently becoming wrong.
    """

    add_rate(
        db,
        input_usd="1.00",
        effective_from=NOW - timedelta(days=60),
        effective_to=NOW - timedelta(days=10),
    )
    add_rate(db, input_usd="0.10", effective_from=NOW - timedelta(days=10))

    old = rate_for(db, model_id="gemini-flash", at=NOW - timedelta(days=30))

    assert Decimal(old.input_cost_per_1m_usd) == Decimal("1.00")


def test_a_rate_that_has_not_started_yet_is_not_used(db):
    add_rate(db, effective_from=NOW + timedelta(days=1))

    assert rate_for(db, model_id="gemini-flash", at=NOW) is None


# ----------------------------------------------------------------------
# Cost arithmetic
# ----------------------------------------------------------------------


def test_cost_is_input_plus_output_per_million(db):
    rate = add_rate(db, input_usd="0.10", output_usd="0.40")

    cost = estimate_cost(rate, prompt_tokens=1_000_000, completion_tokens=1_000_000)

    assert cost == Decimal("0.500000")


def test_a_small_call_does_not_round_to_zero(db):
    rate = add_rate(db, input_usd="0.10", output_usd="0.40")

    cost = estimate_cost(rate, prompt_tokens=1171, completion_tokens=120)

    assert cost > 0


def test_an_unpriced_model_costs_none_not_zero():
    """The distinction this whole design turns on."""

    assert estimate_cost(None, prompt_tokens=1000, completion_tokens=100) is None


# ----------------------------------------------------------------------
# Recording
# ----------------------------------------------------------------------


def test_recording_prices_the_call(db):
    add_rate(db)

    repo.record(
        db,
        model_id="gemini-flash",
        provider="gemini",
        usage=usage_of(prompt=1_000_000),
    )
    db.commit()

    costs = repo.sum_cost_by_model_since(db, NOW - timedelta(days=1))

    assert costs["gemini-flash"] == Decimal("0.100000")


def test_recording_an_unpriced_model_still_records_the_tokens(db):
    """Accounting must not be lost because nobody set a price."""

    repo.record(
        db,
        model_id="never-priced",
        provider="stub",
        usage=usage_of(prompt=500),
    )
    db.commit()

    since = NOW - timedelta(days=1)

    assert repo.sum_tokens_by_model_since(db, since)["never-priced"] == 500
    assert repo.sum_cost_by_model_since(db, since)["never-priced"] is None


def test_every_collected_call_is_recorded(db):
    """
    The regression this phase exists for: a request makes several LLM calls
    and all of them must land, not just generation.
    """

    events = [
        UsageEvent(stage="query_rewrite", usage=usage_of(prompt=139, completion=11)),
        UsageEvent(stage="generation", usage=usage_of(prompt=1171, completion=120)),
    ]

    written = repo.record_collected(
        db,
        events=events,
        default_model_id="gemini-flash",
        default_provider="gemini",
        trace_id="abc123",
        user_id=uuid.uuid4(),
    )
    db.commit()

    assert written == 2

    since = NOW - timedelta(days=1)
    by_stage = repo.sum_tokens_by_stage_since(db, since)

    assert by_stage == {"query_rewrite": 150, "generation": 1291}

    # The whole point: the total exceeds generation alone.
    assert repo.sum_tokens_by_model_since(db, since)["gemini-flash"] == 1441


def test_collected_calls_are_attributed_to_the_default_model(db):
    """
    Rewriting, summarising and the rerank fallback always run on the default
    model, whatever the user picked for the answer. Attributing them to the
    chosen model would bill it for work it did not do.
    """

    repo.record_collected(
        db,
        events=[UsageEvent(stage="query_rewrite", usage=usage_of(prompt=100))],
        default_model_id="gemini-flash",
        default_provider="gemini",
    )
    db.commit()

    totals = repo.sum_tokens_by_model_since(db, NOW - timedelta(days=1))

    assert set(totals) == {"gemini-flash"}


def test_recording_nothing_is_harmless(db):
    assert (
        repo.record_collected(
            db,
            events=[],
            default_model_id="gemini-flash",
            default_provider="gemini",
        )
        == 0
    )
