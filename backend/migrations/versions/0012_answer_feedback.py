"""let readers rate an answer, and tie the rating to its trace

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21 16:30:00.000000

Every metric in this application so far is operational - latency, spend,
how many chunks came back, which retriever answered. None of them can
tell a fast, cheap, well-retrieved *wrong* answer from a right one. A
rating is the only human judgement of quality there is.

Two tables change:

  - conversation_messages gains trace_id, written from the ambient trace
    context when an answer is stored. It is what turns "this answer was
    wrong" into a waterfall an admin can open.
  - answer_feedback holds the ratings. Unlike the telemetry tables it
    carries real foreign keys: it is written synchronously by a user
    looking at the message, so there is no batching and no arrival-order
    problem, and a rating whose message is gone is meaningless.

The unique constraint on (message_id, user_id) makes changing your mind
an update rather than a second vote.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MESSAGE_ID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("trace_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", _MESSAGE_ID, nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Denormalised from the message on purpose: telemetry ages out on
        # its own schedule, and a rating outlives the spans it points at.
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["conversation_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("rating IN ('up', 'down')", name="rating_valid"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"),
    )

    op.create_index("ix_answer_feedback_created_at", "answer_feedback", ["created_at"])
    op.create_index(
        "ix_answer_feedback_rating_created_at",
        "answer_feedback",
        ["rating", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_answer_feedback_rating_created_at", table_name="answer_feedback")
    op.drop_index("ix_answer_feedback_created_at", table_name="answer_feedback")
    op.drop_table("answer_feedback")

    op.drop_column("conversation_messages", "trace_id")
