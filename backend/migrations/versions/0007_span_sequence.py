"""give spans a monotonic position within their trace

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18 12:40:00.000000

A waterfall cannot be ordered by started_at. The wall clock is coarser than
the gap between a parent span and the child it opens, so retrieval,
dense_retrieval and query_embedding routinely carry one identical timestamp
and render scrambled. Durations were never affected - they come from
perf_counter - only the ordering key was.

The index on (trace_id, started_at) is replaced by (trace_id, sequence),
since every read of a single trace wants waterfall order.

Existing rows get sequence 0. They were written before the counter existed
and cannot be reconstructed, so they keep the old ambiguity; nothing else
depends on the column being distinct.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rag_spans",
        sa.Column(
            "sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_index(
        "ix_rag_spans_trace_id_sequence",
        "rag_spans",
        ["trace_id", "sequence"],
    )

    op.drop_index("ix_rag_spans_trace_id_started_at", table_name="rag_spans")


def downgrade() -> None:
    op.create_index(
        "ix_rag_spans_trace_id_started_at",
        "rag_spans",
        ["trace_id", "started_at"],
    )

    op.drop_index("ix_rag_spans_trace_id_sequence", table_name="rag_spans")

    op.drop_column("rag_spans", "sequence")
