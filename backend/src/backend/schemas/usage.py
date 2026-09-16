from datetime import datetime

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


class ModelUsageResponse(BaseModel):
    models: list[ModelUsageInfo]
    generated_at: datetime
