"""
Reads and writes over answer ratings.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import (
    RATING_DOWN,
    RATING_UP,
    AnswerFeedback,
    Conversation,
    ConversationMessage,
)


def find_answer(
    session: Session,
    *,
    message_id: int,
    user_id: uuid.UUID,
) -> ConversationMessage | None:
    """
    The assistant message this user is allowed to rate, if it exists.

    Ownership is checked by joining to the conversation rather than
    trusting a conversation id from the client, and a message belonging to
    someone else comes back as None - so the caller answers 404 and the
    response cannot be used to discover which message ids exist. Same rule
    the conversation and document routes already follow.
    """

    return session.scalar(
        sa.select(ConversationMessage)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(
            ConversationMessage.id == message_id,
            ConversationMessage.role == "assistant",
            Conversation.user_id == user_id,
        )
    )


def get(
    session: Session,
    *,
    message_id: int,
    user_id: uuid.UUID,
) -> AnswerFeedback | None:
    return session.scalar(
        sa.select(AnswerFeedback).where(
            AnswerFeedback.message_id == message_id,
            AnswerFeedback.user_id == user_id,
        )
    )


def record(
    session: Session,
    *,
    message: ConversationMessage,
    user_id: uuid.UUID,
    rating: str,
    comment: str | None,
) -> AnswerFeedback:
    """
    Rate an answer, or change an existing rating.

    Update in place rather than append: a second opinion on the same
    answer replaces the first, it is not a second vote. Reading then
    writing is safe here because the unique constraint is the real
    guarantee - a race loses the insert, not the rating.
    """

    existing = get(session, message_id=message.id, user_id=user_id)

    if existing is not None:
        existing.rating = rating
        existing.comment = comment

        session.flush()

        return existing

    feedback = AnswerFeedback(
        message_id=message.id,
        conversation_id=message.conversation_id,
        user_id=user_id,
        trace_id=message.trace_id,
        rating=rating,
        comment=comment,
    )

    session.add(feedback)
    session.flush()

    return feedback


def remove(session: Session, *, message_id: int, user_id: uuid.UUID) -> bool:
    """Withdraw a rating. True if there was one to withdraw."""

    result = session.execute(
        sa.delete(AnswerFeedback).where(
            AnswerFeedback.message_id == message_id,
            AnswerFeedback.user_id == user_id,
        )
    )

    return bool(result.rowcount)


def ratings_for_messages(
    session: Session,
    *,
    message_ids: list[int],
    user_id: uuid.UUID,
) -> dict[int, str]:
    """
    This reader's own ratings, so a reloaded conversation shows them.

    Scoped to one user on purpose: a rating is private to whoever left it,
    and nobody should be able to see how someone else rated an answer.
    """

    if not message_ids:
        return {}

    rows = session.execute(
        sa.select(AnswerFeedback.message_id, AnswerFeedback.rating).where(
            AnswerFeedback.message_id.in_(message_ids),
            AnswerFeedback.user_id == user_id,
        )
    )

    return {message_id: rating for message_id, rating in rows}


# ----------------------------------------------------------------------
# The monitoring side
# ----------------------------------------------------------------------


def counts_between(
    session: Session,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    """How many of each rating were left in a window."""

    rows = session.execute(
        sa.select(AnswerFeedback.rating, sa.func.count())
        .where(
            AnswerFeedback.created_at >= start,
            AnswerFeedback.created_at < end,
        )
        .group_by(AnswerFeedback.rating)
    )

    counts = {rating: int(count) for rating, count in rows}

    return {
        RATING_UP: counts.get(RATING_UP, 0),
        RATING_DOWN: counts.get(RATING_DOWN, 0),
    }


def answers_in_window(session: Session, start: datetime, end: datetime) -> int:
    """
    Assistant messages produced in the window.

    The denominator for "how often does anyone rate anything at all",
    which is worth knowing before reading anything into the ratio of
    thumbs up to thumbs down.
    """

    return int(
        session.scalar(
            sa.select(sa.func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.role == "assistant",
                ConversationMessage.created_at >= start,
                ConversationMessage.created_at < end,
            )
        )
        or 0
    )


def recent_negative(
    session: Session,
    start: datetime,
    end: datetime,
    *,
    limit: int = 20,
) -> list[AnswerFeedback]:
    """
    The most recent thumbs-down, newest first.

    Each carries the trace that produced the answer, which is the whole
    point: a complaint that opens a waterfall is actionable, a complaint
    that does not is a feeling.
    """

    return list(
        session.scalars(
            sa.select(AnswerFeedback)
            .where(
                AnswerFeedback.rating == RATING_DOWN,
                AnswerFeedback.created_at >= start,
                AnswerFeedback.created_at < end,
            )
            .order_by(AnswerFeedback.created_at.desc())
            .limit(limit)
        ).all()
    )
