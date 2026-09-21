"""
Rating an answer.

The only endpoint in this application that records a human judgement of
quality rather than a measurement. Everything else the monitoring work
added says how the system behaved; this says whether the behaviour was
any good, which no amount of latency and token counting can establish.
"""

import logging

from fastapi import APIRouter, HTTPException, Response, status

from backend.db.repositories import feedback as feedback_repo
from backend.dependencies import CurrentUser, DbSession
from backend.schemas.feedback import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    request: FeedbackRequest,
    session: DbSession,
    user: CurrentUser,
) -> FeedbackResponse:
    """
    Rate an answer, or change a rating already given.

    A message belonging to someone else is reported as missing rather than
    forbidden, so the response cannot be used to enumerate message ids -
    the same rule the conversation and document routes follow.
    """

    message = feedback_repo.find_answer(
        session,
        message_id=request.message_id,
        user_id=user.id,
    )

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer not found.",
        )

    record = feedback_repo.record(
        session,
        message=message,
        user_id=user.id,
        rating=request.rating,
        comment=request.comment,
    )

    session.commit()
    session.refresh(record)

    return FeedbackResponse(
        message_id=record.message_id,
        rating=record.rating,
        comment=record.comment,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/feedback/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_feedback(
    message_id: int,
    session: DbSession,
    user: CurrentUser,
) -> Response:
    """
    Withdraw a rating.

    Idempotent: withdrawing a rating that is not there succeeds. The
    caller wanted no rating to exist, and none does.
    """

    feedback_repo.remove(session, message_id=message_id, user_id=user.id)
    session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
