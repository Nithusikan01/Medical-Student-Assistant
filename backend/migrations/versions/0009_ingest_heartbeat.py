"""give ingestion a heartbeat so a stall can be told from slowness

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-21 12:10:00.000000

A document row is created as `processing` before ingestion starts, and
DocumentService moves it to `ready` or `failed` when ingestion returns. A
killed process returns nothing, so the row stayed `processing` for good -
and since the lexical index is built only from `ready` documents, its
chunks became invisible to BM25 while its vectors stayed live in Pinecone.

`heartbeat_at` is touched as each batch of chunks lands. `updated_at`
cannot serve: ingestion writes to document_chunks, not to this table, so a
healthy twenty-minute ingest and one that died ten seconds in look
identical through it.

Existing `processing` rows get a null heartbeat, which the sweep reads as
"never got that far" and falls back to created_at - so anything already
stuck is reconciled on the first startup after this ships.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_documents_status_heartbeat_at",
        "documents",
        ["status", "heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_status_heartbeat_at", table_name="documents")
    op.drop_column("documents", "heartbeat_at")
