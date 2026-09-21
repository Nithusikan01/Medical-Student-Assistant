import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import Conversation, ConversationMessage

TITLE_MAX_LENGTH = 60


def derive_title(question: str) -> str:
    collapsed = " ".join(question.split())

    if len(collapsed) <= TITLE_MAX_LENGTH:
        return collapsed

    return collapsed[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def get(session: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def list_for_user(
    session: Session,
    user_id: uuid.UUID,
) -> list[Conversation]:
    return list(
        session.scalars(
            sa.select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.created_at.desc(),
            )
        )
    )


def create(
    session: Session,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str | None = None,
) -> Conversation:
    conversation = Conversation(
        id=conversation_id,
        user_id=user_id,
        title=title,
    )

    session.add(conversation)
    session.flush()

    return conversation


def message_counts(
    session: Session,
    conversation_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not conversation_ids:
        return {}

    rows = session.execute(
        sa.select(
            ConversationMessage.conversation_id,
            sa.func.count(ConversationMessage.id),
        )
        .where(ConversationMessage.conversation_id.in_(conversation_ids))
        .group_by(ConversationMessage.conversation_id)
    )

    return {conversation_id: count for conversation_id, count in rows}


def messages_for(
    session: Session,
    conversation_id: uuid.UUID,
) -> list[ConversationMessage]:
    return list(
        session.scalars(
            sa.select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id)
        )
    )


def latest_answer_id(session: Session, conversation_id: uuid.UUID) -> int | None:
    """
    The id of the most recent assistant message in a conversation.

    Returned to the client so an answer can be rated without reloading
    the conversation first - the id is minted inside the memory layer,
    which the router has no handle on.
    """

    return session.scalar(
        sa.select(sa.func.max(ConversationMessage.id)).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "assistant",
        )
    )


def attach_sources_to_latest_answer(
    session: Session,
    conversation_id: uuid.UUID,
    sources: list[dict[str, Any]],
) -> None:
    latest_id = session.scalar(
        sa.select(sa.func.max(ConversationMessage.id)).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "assistant",
        )
    )

    if latest_id is None:
        return

    session.execute(
        sa.update(ConversationMessage)
        .where(ConversationMessage.id == latest_id)
        .values(sources=sources)
    )
