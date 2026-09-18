from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ModelUsageInfo(BaseModel):
    id: str
    label: str
    provider: str

    daily_tokens_used: int
    # None means the model has no configured daily quota (usage is still
    # reported, there's just nothing to compare it against).
    daily_token_limit: int | None

    monthly_tokens_used: int
    monthly_token_limit: int | None

    # None means "no pricing configured for this model", which is a
    # different statement from 0.00 and must not render as free.
    daily_estimated_cost_usd: Decimal | None = None
    monthly_estimated_cost_usd: Decimal | None = None


class StageUsageInfo(BaseModel):
    """
    Tokens by pipeline stage.

    This is the breakdown that answers "why did consumption go up" rather
    than only "by how much" - and the reason it exists at all is that three
    of these stages were previously not counted.
    """

    stage: str
    tokens_used: int


class ModelUsageResponse(BaseModel):
    models: list[ModelUsageInfo]

    # Today's spend by stage. Empty before any query has been answered.
    stages: list[StageUsageInfo] = []

    # False when no model_pricing row applies, so the client can say "not
    # priced" instead of showing a confident zero.
    pricing_configured: bool = False

    generated_at: datetime
