import calendar
from datetime import UTC, datetime

from fastapi import APIRouter

from backend.db.repositories import usage
from backend.dependencies import AdminUser, AllGenerationModels, DbSession
from backend.schemas import ModelUsageInfo, ModelUsageResponse, StageUsageInfo
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

    daily_cost = usage.sum_cost_by_model_since(session, day_start)
    monthly_cost = usage.sum_cost_by_model_since(session, month_start)

    # These totals now include query rewriting, summarisation and the rerank
    # fallback, which were never counted before. Expect them to be higher
    # than they were - that is the correction, not a regression.
    stage_totals = usage.sum_tokens_by_stage_since(session, day_start)

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
                daily_estimated_cost_usd=daily_cost.get(model.id),
                monthly_estimated_cost_usd=monthly_cost.get(model.id),
            )
        )

    return ModelUsageResponse(
        models=results,
        stages=[
            StageUsageInfo(stage=stage, tokens_used=tokens)
            for stage, tokens in sorted(
                stage_totals.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ],
        # Distinguishes "nothing cost anything" from "nothing is priced".
        pricing_configured=any(cost is not None for cost in monthly_cost.values()),
        generated_at=now,
    )
