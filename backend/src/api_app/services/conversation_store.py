import uuid
from typing import Any

import sqlalchemy as sa
from rag_application.conversation.memory import ConversationMemory
from rag_application.conversation.schemas import ChatMessage
from sqlalchemy.orm import Session, sessionmaker

from api_app.db.models import Conversation, ConversationMessage


class PersistentConversationMemory(ConversationMemory):
    """
    Conversation memory backed by the database.

    `messages` deliberately holds only the turns *after* the stored summary's
    checkpoint, because HistoryAwareRAGService summarises whenever
    len(messages) reaches its trigger. Hydrating the full history would leave
    that condition permanently true and fire an extra LLM call every turn
    forever. Prompt context comes from `_recent` instead, which tracks the
    last N messages overall.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        conversation_id: uuid.UUID,
        *,
        max_recent_messages: int = 6,
    ) -> None:
        super().__init__(max_recent_messages=max_recent_messages)

        self._session_factory = session_factory
        self.conversation_id = conversation_id
        self.last_assistant_message_id: int | None = None
        self._recent: list[ChatMessage] = []

        self._hydrate()

    def _hydrate(self) -> None:
        with self._session_factory() as session:
            conversation = session.get(Conversation, self.conversation_id)

            if conversation is None:
                return

            self.summary = conversation.summary or ""

            since = sa.select(ConversationMessage).where(
                ConversationMessage.conversation_id == self.conversation_id
            )

            if conversation.summary_checkpoint_message_id is not None:
                since = since.where(
                    ConversationMessage.id > conversation.summary_checkpoint_message_id
                )

            self.messages = [
                ChatMessage(role=row.role, content=row.content)
                for row in session.scalars(since.order_by(ConversationMessage.id))
            ]

            newest = session.scalars(
                sa.select(ConversationMessage)
                .where(ConversationMessage.conversation_id == self.conversation_id)
                .order_by(ConversationMessage.id.desc())
                .limit(self.max_recent_messages)
            ).all()

            self._recent = [
                ChatMessage(role=row.role, content=row.content)
                for row in reversed(newest)
            ]

    def add_message(self, role: str, content: str) -> None:
        super().add_message(role, content)

        with self._session_factory() as session:
            row = ConversationMessage(
                conversation_id=self.conversation_id,
                role=role,
                content=content,
            )

            session.add(row)
            session.flush()

            session.execute(
                sa.update(Conversation)
                .where(Conversation.id == self.conversation_id)
                .values(last_message_at=sa.func.now())
            )

            session.commit()

            if role == "assistant":
                self.last_assistant_message_id = row.id

        self._recent = (self._recent + [ChatMessage(role=role, content=content)])[
            -self.max_recent_messages :
        ]

    def get_recent_messages(self) -> list[ChatMessage]:
        return self._recent

    def update_summary(self, summary: str) -> None:
        super().update_summary(summary)

        with self._session_factory() as session:
            newest_id = session.scalar(
                sa.select(sa.func.max(ConversationMessage.id)).where(
                    ConversationMessage.conversation_id == self.conversation_id
                )
            )

            session.execute(
                sa.update(Conversation)
                .where(Conversation.id == self.conversation_id)
                .values(
                    summary=summary,
                    summary_checkpoint_message_id=newest_id,
                )
            )

            session.commit()

        # Everything up to the checkpoint is now represented by the summary,
        # so the trigger starts counting again from zero.
        self.messages = []

    def attach_sources(self, sources: list[dict[str, Any]]) -> None:
        if self.last_assistant_message_id is None:
            return

        with self._session_factory() as session:
            session.execute(
                sa.update(ConversationMessage)
                .where(ConversationMessage.id == self.last_assistant_message_id)
                .values(sources=sources)
            )

            session.commit()


class PersistentConversationStore:
    """
    Builds database-backed memory on demand.

    Holds a session factory rather than a session, because the RAG service is
    a process-wide singleton that outlives any single request.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_memory(
        self,
        conversation_id: str,
    ) -> PersistentConversationMemory:
        return PersistentConversationMemory(
            self._session_factory,
            uuid.UUID(str(conversation_id)),
        )
