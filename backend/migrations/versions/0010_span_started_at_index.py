"""index spans by age so retention can sweep orphans

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21 14:05:00.000000

Retention deletes a trace and its spans together, selecting the traces
first and removing their spans by trace_id - which the existing
(trace_id, sequence) index already serves.

Orphan spans are the case that needs this one. The telemetry sink drops
records when its queue is full and writes the trace row last, so a burst
can leave spans whose trace never arrived. Those are swept by age alone,
and ix_rag_spans_stage_started_at cannot answer that: started_at is not
its leading column.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_rag_spans_started_at", "rag_spans", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_spans_started_at", table_name="rag_spans")
