import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_app.db.base import Base

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# BIGSERIAL on Postgres; SQLite needs plain INTEGER for rowid autoincrement.
_MessageId = sa.BigInteger().with_variant(sa.Integer, "sqlite")


class Conversation(Base):
    __tablename__ = "conversations"

    # Supplied by the client so a chat can be addressed before its first
    # message has been stored.
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(sa.String(200))

    summary: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        default="",
        server_default="",
    )

    # Messages at or before this id are already folded into `summary`.
    # Without it the summariser would re-fire on every turn once the history
    # passes the trigger length.
    summary_checkpoint_message_id: Mapped[int | None] = mapped_column(_MessageId)

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

    last_message_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.id",
    )

    __table_args__ = (
        sa.Index(
            "ix_conversations_user_id_last_message_at",
            "user_id",
            sa.text("last_message_at DESC"),
        ),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(
        _MessageId,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    content: Mapped[str] = mapped_column(sa.Text, nullable=False)

    # Retrieved chunks for assistant turns, so the UI can replay citations
    # without re-running retrieval.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(sa.JSON)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        sa.CheckConstraint(
            f"role IN ('{ROLE_USER}', '{ROLE_ASSISTANT}')",
            name="role_valid",
        ),
        sa.Index(
            "ix_conversation_messages_conversation_id_id",
            "conversation_id",
            "id",
        ),
    )
