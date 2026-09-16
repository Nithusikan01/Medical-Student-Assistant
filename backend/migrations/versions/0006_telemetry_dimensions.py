"""promote telemetry status_code and route to columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17 01:10:00.000000

Both values were already being recorded, inside the trace's JSON metadata.
They move into columns here because the operational metrics group by them -
success and error rates by status class, latency by route - and filtering
inside a JSON column needs dialect-specific SQL that the SQLite-backed test
suite could not exercise.

No backfill: rag_traces was added one revision ago and, at the time of
writing, has not been deployed, so there are no rows whose metadata would
need moving. Were that not the case, existing rows would simply report a
null status_code and route until they aged out of the retention window.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rag_traces", sa.Column("status_code", sa.Integer(), nullable=True))
    op.add_column("rag_traces", sa.Column("route", sa.String(length=256), nullable=True))

    op.create_index(
        "ix_rag_traces_route_started_at",
        "rag_traces",
        ["route", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_traces_route_started_at", table_name="rag_traces")

    op.drop_column("rag_traces", "route")
    op.drop_column("rag_traces", "status_code")
