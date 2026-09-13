import uuid

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, status

from backend.db.models import Conversation
from backend.db.repositories import conversations
from backend.dependencies import CurrentUser, DbSession
from backend.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    ConversationUpdateRequest,
)

router = APIRouter()

NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Conversation not found.",
)


def _owned_or_404(
    session,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    """
    A conversation belonging to someone else is reported as missing rather
    than forbidden, so the response cannot be used to discover which ids
    exist.
    """

    conversation = conversations.get(session, conversation_id)

    if conversation is None or conversation.user_id != user_id:
        raise NOT_FOUND

    return conversation


@router.get(
    "/conversations",
    response_model=list[ConversationSummaryResponse],
)
def list_conversations(
    session: DbSession,
    user: CurrentUser,
) -> list[ConversationSummaryResponse]:
    rows = conversations.list_for_user(session, user.id)
    counts = conversations.message_counts(session, [row.id for row in rows])

    return [
        ConversationSummaryResponse(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            last_message_at=row.last_message_at,
            message_count=counts.get(row.id, 0),
        )
        for row in rows
    ]


@router.post(
    "/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ConversationDetailResponse:
    conversation = conversations.create(
        session,
        conversation_id=uuid.uuid4(),
        user_id=user.id,
        title=payload.title,
    )

    session.commit()

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        messages=[],
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
)
def get_conversation(
    conversation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> ConversationDetailResponse:
    conversation = _owned_or_404(session, conversation_id, user.id)

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        messages=[
            ConversationMessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                sources=message.sources,
                created_at=message.created_at,
            )
            for message in conversations.messages_for(session, conversation.id)
        ],
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationSummaryResponse,
)
def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ConversationSummaryResponse:
    conversation = _owned_or_404(session, conversation_id, user.id)

    conversation.title = payload.title
    session.commit()

    return ConversationSummaryResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> None:
    conversation = _owned_or_404(session, conversation_id, user.id)

    session.execute(sa.delete(Conversation).where(Conversation.id == conversation.id))
    session.commit()
