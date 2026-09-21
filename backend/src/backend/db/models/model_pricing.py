import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ModelPricing(Base):
    """
    What a model costs, per million tokens.

    A table rather than constants because prices change and are corrected,
    and because a deployment must be able to fix a wrong rate without a code
    change - section 14 of the observability spec.

    Rates are USD. Both providers quote in USD, and a currency column that
    always reads "USD" is the kind of field section 55 warns against; add one
    when a provider actually bills in something else.

    Rows are time-bounded rather than mutated: `effective_to` closes a rate
    and a new row opens the next one, so a historical cost stays explicable
    after a price change instead of silently becoming wrong.
    """

    __tablename__ = "model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # The catalog id ("gemini-flash"), matching generation_usage_events, not
    # the provider's raw model string - the same reasoning as that table.
    model_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    provider: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # Numeric, not Float: money. Four decimal places covers rates quoted in
    # cents per million tokens.
    input_cost_per_1m_usd: Mapped[float] = mapped_column(
        sa.Numeric(12, 4),
        nullable=False,
    )

    output_cost_per_1m_usd: Mapped[float] = mapped_column(
        sa.Numeric(12, 4),
        nullable=False,
    )

    effective_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    # Open-ended while this is the current rate.
    effective_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    # Where the number came from, so a future reader can re-check it rather
    # than trusting it. Prices are the easiest thing here to get wrong.
    source: Mapped[str | None] = mapped_column(sa.Text)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    __table_args__ = (
        sa.Index(
            "ix_model_pricing_model_id_effective_from",
            "model_id",
            "effective_from",
        ),
    )
