from rag_application.conversation.memory import ConversationMemory
from rag_application.conversation.session_manager import SessionManager
from rag_application.conversation.store import ConversationStore


def test_session_manager_satisfies_conversation_store():
    assert isinstance(SessionManager(), ConversationStore)


def test_session_manager_returns_stable_memory_per_conversation():
    manager = SessionManager()

    first = manager.get_memory("conversation-a")
    second = manager.get_memory("conversation-a")
    other = manager.get_memory("conversation-b")

    assert isinstance(first, ConversationMemory)
    assert first is second
    assert other is not first
