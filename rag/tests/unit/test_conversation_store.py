from rag.conversation.memory import ConversationMemory
from rag.conversation.session_manager import SessionManager
from rag.conversation.store import ConversationStore


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


def test_summarising_resets_the_pending_turns():
    """
    The engine's own memory used to keep every turn in `messages` after a
    summary, so once a conversation reached the trigger length the service
    summarised again on every single turn.
    """

    memory = ConversationMemory()

    for index in range(12):
        memory.add_message("user", f"turn {index}")

    memory.update_summary("summary")

    assert memory.messages == []
    assert memory.get_summary() == "summary"


def test_recent_window_survives_a_summary():
    memory = ConversationMemory(max_recent_messages=3)

    for index in range(5):
        memory.add_message("user", f"turn {index}")

    memory.update_summary("summary")

    assert [m.content for m in memory.get_recent_messages()] == [
        "turn 2",
        "turn 3",
        "turn 4",
    ]


def test_summarizer_folds_in_every_pending_turn_not_just_the_window():
    from rag.conversation.summarizer import ConversationSummarizer
    from rag.llm.schemas import LLMResponse

    class RecordingGenerator:
        prompt = ""

        def generate(self, prompt):
            self.prompt = prompt
            return LLMResponse(text="summary")

    memory = ConversationMemory(max_recent_messages=6)

    for index in range(12):
        memory.add_message("user", f"turn-{index:02d}")

    generator = RecordingGenerator()
    ConversationSummarizer(generator).summarize(memory)

    for index in range(12):
        assert f"turn-{index:02d}" in generator.prompt
