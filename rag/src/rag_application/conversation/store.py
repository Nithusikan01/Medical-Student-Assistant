from typing import Protocol, runtime_checkable

from rag_application.conversation.memory import ConversationMemory


@runtime_checkable
class ConversationStore(Protocol):
    """
    Supplies per-conversation memory to the RAG service.

    SessionManager satisfies this with in-process storage. An application
    that needs conversations to outlive the process supplies its own
    database-backed implementation instead. The protocol lives here so the
    engine never has to import the web layer to be persisted.
    """

    def get_memory(self, conversation_id: str) -> ConversationMemory: ...
