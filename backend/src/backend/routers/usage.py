import calendar
from datetime import UTC, datetime

from fastapi import APIRouter

from backend.db.repositories import usage
from backend.dependencies import AdminUser, AllGenerationModels, DbSession
from backend.schemas import ModelUsageInfo, ModelUsageResponse
from backend.wiring.rag_factory import daily_token_limit

router = APIRouter()


@router.get("/usage/models", response_model=ModelUsageResponse)
def get_model_usage(
    session: DbSession,
    models: AllGenerationModels,
    admin: AdminUser,
) -> ModelUsageResponse:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    daily_totals = usage.sum_tokens_by_model_since(session, day_start)
    monthly_totals = usage.sum_tokens_by_model_since(session, month_start)

    results = []

    for model in models:
        limit = daily_token_limit(model.id)

        results.append(
            ModelUsageInfo(
                id=model.id,
                label=model.label,
                provider=model.provider,
                daily_tokens_used=daily_totals.get(model.id, 0),
                daily_token_limit=limit,
                monthly_tokens_used=monthly_totals.get(model.id, 0),
                # Groq's quotas reset daily, not monthly, so this is a
                # derived reference ceiling (limit x days-in-month), not a
                # real provider-side monthly cap.
                monthly_token_limit=(
                    limit * days_in_month if limit is not None else None
                ),
            )
        )

    return ModelUsageResponse(models=results, generated_at=now)
