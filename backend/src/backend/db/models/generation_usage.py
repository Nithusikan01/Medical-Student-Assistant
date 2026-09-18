import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

# The LLM call sites this application has. Every one of them spends
# tokens; only the first was ever recorded before.
STAGE_GENERATION = "generation"
STAGE_QUERY_REWRITE = "query_rewrite"
STAGE_SUMMARIZATION = "summarization"
STAGE_RERANKING = "reranking"


class GenerationUsageEvent(Base):
    """
    One generation call's token accounting.

    One row per query, rather than a running per-model counter, so daily and
    monthly totals are both just a SUM(...) WHERE created_at >= window_start
    - no separate reset job, and no drift between the two windows.
    """

    __tablename__ = "generation_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # The catalog id (e.g. "groq-gpt-oss-120b"), not the raw provider model
    # name, so it lines up with rag_factory's _GENERATION_MODEL_SPECS even
    # if the underlying provider model string changes later.
    model_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    provider: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # Which LLM call this was. Until this column existed only the final
    # answer was recorded, so the table - and the admin dashboard built on
    # it - understated real spend by everything query rewriting,
    # summarisation and the Gemini rerank fallback consumed.
    stage: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default=STAGE_GENERATION,
        server_default=STAGE_GENERATION,
    )

    # Ties spend back to the request that incurred it. Nullable because a
    # call made outside a traced request still has to be counted.
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))

    # For cost-by-user. No foreign key, for the same reason the telemetry
    # tables have none: this is an accounting record and must survive the
    # account being deleted.
    user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)

    prompt_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # Null when no pricing row covered this model at this time. Null and zero
    # are different answers - "not priced" must not render as "free".
    #
    # "Estimated" is literal: it is computed from the model_pricing table,
    # not read off a provider invoice.
    estimated_cost_usd: Mapped[float | None] = mapped_column(sa.Numeric(12, 6))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    __table_args__ = (
        sa.Index(
            "ix_generation_usage_events_model_id_created_at",
            "model_id",
            "created_at",
        ),
        sa.Index(
            "ix_generation_usage_events_stage_created_at",
            "stage",
            "created_at",
        ),
        sa.Index("ix_generation_usage_events_trace_id", "trace_id"),
    )
