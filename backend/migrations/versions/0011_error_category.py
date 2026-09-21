"""record what kind of failure a trace or span hit

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-21 15:40:00.000000

error_type already said which exception class was raised. That names the
failure without saying what to do about it: a Gemini 429, a Pinecone
timeout and a malformed PDF were three names in one undifferentiated
bucket, and only the first of the three is fixed by waiting.

error_category is the operator-facing axis - rate_limit, timeout,
upstream, auth, validation, internal - classified from exception type and
status code, never from message text.

A column rather than a metadata key because the error panel groups by it
and an alert has to be able to filter on it in SQL.

Existing rows keep a null category. Null reads as "classified before this
shipped", which is honest; backfilling from error_type would invent a
classification for failures nobody classified at the time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("rag_traces", "rag_spans"):
        op.add_column(table, sa.Column("error_category", sa.String(32), nullable=True))

    op.create_index(
        "ix_rag_spans_error_category",
        "rag_spans",
        ["error_category", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_spans_error_category", table_name="rag_spans")

    for table in ("rag_traces", "rag_spans"):
        op.drop_column(table, "error_category")
