"""
What the summary is made from, and how often it is made.

The summary replaces every turn since the last one, so it has to be built
from all of them. It used to be built from the prompt's recent window - six
turns - while twelve triggered it, and the other six were lost from the
conversation's long-term memory for good.
"""

from unittest.mock import Mock

from rag.conversation.memory import ConversationMemory
from rag.conversation.session_manager import SessionManager
from rag.conversation.summarizer import ConversationSummarizer
from rag.llm.schemas import LLMResponse
from rag.services.history_aware_rag_service import HistoryAwareRAGService
from tests.unit.helpers import make_retrieved_chunk

TRIGGER = HistoryAwareRAGService.SUMMARY_TRIGGER


def recording_generator(text: str = "summary so far") -> Mock:
    generator = Mock()
    generator.generate.return_value = LLMResponse(text=text)
    return generator


def test_summarising_reads_every_turn_since_the_last_summary():
    memory = ConversationMemory(max_recent_messages=6)

    for turn in range(TRIGGER):
        memory.add_message("user", f"turn {turn}")

    generator = recording_generator()
    ConversationSummarizer(generator).summarize(memory)

    prompt = generator.generate.call_args.args[0]

    # Turn 0 sits outside the six-turn window; it must still be summarised.
    assert all(f"turn {turn}\n" in prompt + "\n" for turn in range(TRIGGER))


def test_a_summary_restarts_the_count_but_keeps_the_prompt_context():
    memory = ConversationMemory(max_recent_messages=4)

    for turn in range(TRIGGER):
        memory.add_message("user", f"turn {turn}")

    memory.update_summary("They asked twelve questions.")

    assert memory.messages == []
    assert [m.content for m in memory.get_recent_messages()] == [
        "turn 8",
        "turn 9",
        "turn 10",
        "turn 11",
    ]


def test_the_recent_window_is_capped_without_duplicates():
    memory = ConversationMemory(max_recent_messages=3)

    for turn in range(5):
        memory.add_message("user", f"turn {turn}")

    assert [m.content for m in memory.get_recent_messages()] == [
        "turn 2",
        "turn 3",
        "turn 4",
    ]
    assert len(memory.messages) == 5


def test_a_zero_window_means_no_recent_context():
    memory = ConversationMemory(max_recent_messages=0)
    memory.add_message("user", "hello there")

    assert memory.get_recent_messages() == []


def test_a_long_conversation_is_summarised_once_per_block_not_every_turn():
    # Before the fix, the engine's own memory never emptied `messages`, so
    # every turn after the twelfth called the summariser again.
    summary_generator = recording_generator("summary so far")
    query_service = Mock()
    query_service.search.return_value = [make_retrieved_chunk()]
    rewriter = Mock()
    rewriter.rewrite.return_value = "standalone question"

    service = HistoryAwareRAGService(
        query_service=query_service,
        generator=recording_generator("an answer"),
        session_manager=SessionManager(),
        query_rewriter=rewriter,
        summarizer=ConversationSummarizer(summary_generator),
    )

    # Each question adds two messages: the question and its answer.
    for turn in range(TRIGGER):
        service.answer(conversation_id="c", question=f"question number {turn}?")

    assert summary_generator.generate.call_count == 2
