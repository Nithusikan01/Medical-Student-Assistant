"""record the pages a chunk spans; drop chunk fields nothing ever set

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-15 18:00:00.000000

Chunks are now cut from a document's whole text rather than page by page,
so one can start on one page and end on the next. end_page_number records
where it ends; it is null for chunks ingested before, which keep meaning
"the page in page_number".

section_title, heading_level and language were declared from the first
migration but never written with anything but their defaults: extracted
PDF text carries no headings, and nothing detected a language. They are
dropped rather than kept looking meaningful.

Re-ingesting a document is not required. It is only needed to give that
document's existing chunks a page range and to have them re-cut across page
breaks - and it changes what each of its chunk ids points at, so
evaluation labels into that document need relabelling afterwards.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("document_chunks") as batch:
        batch.add_column(sa.Column("end_page_number", sa.Integer(), nullable=True))
        batch.drop_column("section_title")
        batch.drop_column("heading_level")
        batch.drop_column("language")


def downgrade() -> None:
    with op.batch_alter_table("document_chunks") as batch:
        batch.add_column(
            sa.Column(
                "language",
                sa.String(length=16),
                server_default="en",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("heading_level", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("section_title", sa.String(length=512), nullable=True)
        )
        batch.drop_column("end_page_number")
