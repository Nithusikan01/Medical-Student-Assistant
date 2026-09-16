import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


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

    prompt_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)

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
    )
