"""per-stage token accounting and a configurable pricing table

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-18 12:55:00.000000

Two changes, one purpose: make recorded spend match real spend, and give it
a cost.

generation_usage_events gains `stage`, because until now only the final
answer was recorded. Query rewriting fires on every question, summarisation
every twelve messages, and the Gemini reranker whenever hosted reranking
fails - all three spend tokens that the table, and the admin dashboard built
on it, never counted. Existing rows default to 'generation', which is what
they were.

Expect the daily totals on the admin usage page to *rise* after this ships.
That is the correction, not a regression.

model_pricing is created empty, deliberately. Seeding it with rates nobody
has checked would put believable wrong money on a dashboard, which is worse
than showing nothing: estimated_cost_usd stays NULL until an operator
populates it, and NULL is rendered as "not priced" rather than as zero. See
backend/scripts/seed_model_pricing.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("input_cost_per_1m_usd", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("output_cost_per_1m_usd", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_pricing")),
    )
    op.create_index(
        "ix_model_pricing_model_id_effective_from",
        "model_pricing",
        ["model_id", "effective_from"],
    )

    op.add_column(
        "generation_usage_events",
        sa.Column(
            "stage",
            sa.String(length=32),
            nullable=False,
            server_default="generation",
        ),
    )
    op.add_column(
        "generation_usage_events",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generation_usage_events",
        sa.Column("user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "generation_usage_events",
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_generation_usage_events_stage_created_at",
        "generation_usage_events",
        ["stage", "created_at"],
    )
    op.create_index(
        "ix_generation_usage_events_trace_id",
        "generation_usage_events",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generation_usage_events_trace_id",
        table_name="generation_usage_events",
    )
    op.drop_index(
        "ix_generation_usage_events_stage_created_at",
        table_name="generation_usage_events",
    )

    op.drop_column("generation_usage_events", "estimated_cost_usd")
    op.drop_column("generation_usage_events", "user_id")
    op.drop_column("generation_usage_events", "trace_id")
    op.drop_column("generation_usage_events", "stage")

    op.drop_index("ix_model_pricing_model_id_effective_from", table_name="model_pricing")
    op.drop_table("model_pricing")
