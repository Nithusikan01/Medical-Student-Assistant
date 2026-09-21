import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

RATING_UP = "up"
RATING_DOWN = "down"

RATINGS = (RATING_UP, RATING_DOWN)

# Long enough for a sentence about what was wrong, short enough that this
# stays a rating rather than becoming a second chat.
MAX_COMMENT_LENGTH = 1000


class AnswerFeedback(Base):
    """
    What a reader thought of one answer.

    The only human judgement of quality anywhere in this application.
    Every other metric is operational - latency, spend, how many chunks
    came back - and none of them can tell a fast, cheap, well-retrieved
    wrong answer from a right one.

    Unlike the telemetry tables this one carries real foreign keys. It is
    written synchronously, inside the request, by a user who is looking at
    the message right now; there is no batching and no arrival-order
    problem to design around, and a rating whose message has been deleted
    is meaningless rather than merely orphaned.

    `trace_id` is denormalised from the message rather than joined for.
    Telemetry ages out on its own schedule, so the id has to survive here
    on its own - and a rating is worth keeping long after the spans it
    points at have been pruned.
    """

    __tablename__ = "answer_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    message_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer, "sqlite"),
        sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The request that produced the answer, copied from the message.
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))

    rating: Mapped[str] = mapped_column(sa.String(8), nullable=False)

    # User-written text, and the only free text this application stores
    # from a reader. Deliberately not telemetry metadata: it lives here,
    # under ordinary retention, outside the sanitiser's path, and is never
    # attached to a span.
    comment: Mapped[str | None] = mapped_column(sa.String(MAX_COMMENT_LENGTH))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    __table_args__ = (
        sa.CheckConstraint(
            f"rating IN ('{RATING_UP}', '{RATING_DOWN}')",
            name="rating_valid",
        ),
        # One rating per answer per person. Changing your mind updates the
        # row; it does not add a second vote.
        sa.UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"),
        sa.Index("ix_answer_feedback_created_at", "created_at"),
        sa.Index("ix_answer_feedback_rating_created_at", "rating", "created_at"),
    )
