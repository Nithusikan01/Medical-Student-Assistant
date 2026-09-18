import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
from rag.llm.metering import UsageEvent
from rag.llm.schemas import TokenUsage
from sqlalchemy.orm import Session

from backend.db.models import STAGE_GENERATION, GenerationUsageEvent
from backend.services.pricing import estimate_cost, rate_for


def record(
    session: Session,
    *,
    model_id: str,
    provider: str,
    usage: TokenUsage,
    stage: str = STAGE_GENERATION,
    trace_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """
    Record one LLM call's spend, priced at the rate in effect right now.

    `stage` defaults to generation so the original single call site keeps its
    meaning; every other call site passes its own.
    """

    now = datetime.now(UTC)

    session.add(
        GenerationUsageEvent(
            model_id=model_id,
            provider=provider,
            stage=stage,
            trace_id=trace_id,
            user_id=user_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=estimate_cost(
                rate_for(session, model_id=model_id, at=now),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            ),
        )
    )
    session.flush()


def record_collected(
    session: Session,
    *,
    events: list[UsageEvent],
    default_model_id: str,
    default_provider: str,
    trace_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> int:
    """
    Record every LLM call a request made.

    The metering wrapper reports the provider's own model string; the catalog
    id is what this table keys on, so an event whose model matches the one
    the user picked is attributed to that catalog id and anything else - the
    rewriter, the summariser, the rerank fallback, all of which run on the
    default model regardless of what the user selected - falls back to the
    default. Getting this wrong would bill a user's chosen model for work it
    did not do.
    """

    for event in events:
        session.add(
            GenerationUsageEvent(
                model_id=default_model_id,
                provider=event.provider or default_provider,
                stage=event.stage,
                trace_id=trace_id,
                user_id=user_id,
                prompt_tokens=event.usage.prompt_tokens,
                completion_tokens=event.usage.completion_tokens,
                total_tokens=event.usage.total_tokens,
                estimated_cost_usd=estimate_cost(
                    rate_for(
                        session,
                        model_id=default_model_id,
                        at=datetime.now(UTC),
                    ),
                    prompt_tokens=event.usage.prompt_tokens,
                    completion_tokens=event.usage.completion_tokens,
                ),
            )
        )

    session.flush()

    return len(events)


def sum_tokens_by_model_since(session: Session, since: datetime) -> dict[str, int]:
    """
    Total tokens per model_id for events at or after `since`.

    A model with no rows in the window is simply absent from the result -
    the caller treats that as zero.
    """

    rows = session.execute(
        sa.select(
            GenerationUsageEvent.model_id,
            sa.func.sum(GenerationUsageEvent.total_tokens),
        )
        .where(GenerationUsageEvent.created_at >= since)
        .group_by(GenerationUsageEvent.model_id)
    )

    return {model_id: int(total) for model_id, total in rows}


def sum_cost_by_model_since(
    session: Session,
    since: datetime,
) -> dict[str, Decimal | None]:
    """
    Estimated spend per model_id since `since`.

    A model whose rows are all unpriced maps to None rather than to zero, so
    the caller can say "not priced" instead of implying the calls were free.
    """

    rows = session.execute(
        sa.select(
            GenerationUsageEvent.model_id,
            sa.func.sum(GenerationUsageEvent.estimated_cost_usd),
            sa.func.count(GenerationUsageEvent.estimated_cost_usd),
        )
        .where(GenerationUsageEvent.created_at >= since)
        .group_by(GenerationUsageEvent.model_id)
    )

    return {
        model_id: (Decimal(total) if priced else None)
        for model_id, total, priced in rows
    }


def sum_tokens_by_stage_since(session: Session, since: datetime) -> dict[str, int]:
    """
    Total tokens per stage - the breakdown that answers "why did consumption
    go up", rather than only "by how much".
    """

    rows = session.execute(
        sa.select(
            GenerationUsageEvent.stage,
            sa.func.sum(GenerationUsageEvent.total_tokens),
        )
        .where(GenerationUsageEvent.created_at >= since)
        .group_by(GenerationUsageEvent.stage)
    )

    return {stage: int(total) for stage, total in rows}
