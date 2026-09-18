"""
Turning token counts into money.

Cost is computed and stored at write time, from whichever pricing row was in
effect. Two reasons: what a call cost is a fact about the moment it happened,
so a later price change must not silently rewrite history; and reading it back
would otherwise mean an as-of join on every dashboard query.

The word "estimated" is literal throughout - these figures come from a table
this application maintains, not from a provider invoice. Section 14 of the
observability spec asks for that distinction to be kept visible, so the
column, the schema field and the UI all say "estimated".
"""

import logging
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import ModelPricing

logger = logging.getLogger(__name__)

TOKENS_PER_UNIT = Decimal(1_000_000)

# Money, so Decimal rather than float, and six places to keep a single cheap
# call from rounding to zero.
COST_PRECISION = Decimal("0.000001")


def rate_for(
    session: Session,
    *,
    model_id: str,
    at: datetime,
) -> ModelPricing | None:
    """
    The pricing row covering `model_id` at `at`, or None.

    None is a real answer - "this model has no configured price" - and the
    caller must keep it distinct from zero. A model nobody has priced costing
    nothing is exactly the kind of believable wrong number a cost dashboard
    should never show.
    """

    return session.scalars(
        sa.select(ModelPricing)
        .where(
            sa.and_(
                ModelPricing.model_id == model_id,
                ModelPricing.effective_from <= at,
                sa.or_(
                    ModelPricing.effective_to.is_(None),
                    ModelPricing.effective_to > at,
                ),
            )
        )
        .order_by(ModelPricing.effective_from.desc())
        .limit(1)
    ).first()


def estimate_cost(
    pricing: ModelPricing | None,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal | None:
    """
    Cost in USD for one call, or None when the model is not priced.
    """

    if pricing is None:
        return None

    try:
        input_cost = (
            Decimal(prompt_tokens)
            / TOKENS_PER_UNIT
            * Decimal(pricing.input_cost_per_1m_usd)
        )
        output_cost = (
            Decimal(completion_tokens)
            / TOKENS_PER_UNIT
            * Decimal(pricing.output_cost_per_1m_usd)
        )

        return (input_cost + output_cost).quantize(COST_PRECISION)
    except Exception:
        # A malformed rate must not stop the usage row being written: the
        # token counts are the part that has to survive.
        logger.exception("Could not estimate cost for model '%s'.", pricing.model_id)
        return None
