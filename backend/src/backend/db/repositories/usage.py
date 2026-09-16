from datetime import datetime

import sqlalchemy as sa
from rag.llm.schemas import TokenUsage
from sqlalchemy.orm import Session

from backend.db.models import GenerationUsageEvent


def record(
    session: Session,
    *,
    model_id: str,
    provider: str,
    usage: TokenUsage,
) -> None:
    session.add(
        GenerationUsageEvent(
            model_id=model_id,
            provider=provider,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
    )
    session.flush()


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
