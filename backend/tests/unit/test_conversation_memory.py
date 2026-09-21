"""
Database-backed conversation memory.

The interesting property here is the summary checkpoint. HistoryAwareRAGService
summarises whenever `len(memory.messages)` reaches its trigger, so a naive
implementation that hydrated the whole history would leave that condition
permanently true and fire an extra LLM call on every single turn, forever.
"""

import uuid

import sqlalchemy as sa

from backend.db.models import Conversation, ConversationMessage
from backend.services.conversation_store import (
    PersistentConversationMemory,
    PersistentConversationStore,
)

TRIGGER = 12  # HistoryAwareRAGService.SUMMARY_TRIGGER


def make_conversation(session_factory, user_id) -> uuid.UUID:
    conversation_id = uuid.uuid4()

    with session_factory() as session:
        session.add(Conversation(id=conversation_id, user_id=user_id))
        session.commit()

    return conversation_id


def memory_for(session_factory, conversation_id, **kwargs):
    return PersistentConversationMemory(session_factory, conversation_id, **kwargs)


def stored_messages(db, conversation_id) -> list[ConversationMessage]:
    return list(
        db.scalars(
            sa.select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id)
        )
    )


def test_messages_are_written_through_to_the_database(session_factory, user, db):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    memory.add_message("user", "What is the dose?")
    memory.add_message("assistant", "500 mg.")

    rows = stored_messages(db, conversation_id)

    assert [(row.role, row.content) for row in rows] == [
        ("user", "What is the dose?"),
        ("assistant", "500 mg."),
    ]


def test_a_new_memory_rehydrates_the_conversation(session_factory, user):
    conversation_id = make_conversation(session_factory, user.id)

    first = memory_for(session_factory, conversation_id)
    first.add_message("user", "What is the dose?")
    first.add_message("assistant", "500 mg.")

    reopened = memory_for(session_factory, conversation_id)

    assert [message.content for message in reopened.messages] == [
        "What is the dose?",
        "500 mg.",
    ]
    assert [message.content for message in reopened.get_recent_messages()] == [
        "What is the dose?",
        "500 mg.",
    ]


def test_recent_messages_are_capped(session_factory, user):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id, max_recent_messages=4)

    for index in range(10):
        memory.add_message("user", f"question {index}")

    recent = memory.get_recent_messages()

    assert len(recent) == 4
    assert recent[-1].content == "question 9"


def test_updating_the_summary_moves_the_checkpoint_and_clears_the_trigger(
    session_factory, user, db
):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    for index in range(TRIGGER):
        memory.add_message("user", f"question {index}")

    assert len(memory.messages) == TRIGGER

    memory.update_summary("They asked twelve questions.")

    assert memory.messages == [], "the trigger must start counting again from zero"

    db.expire_all()
    conversation = db.get(Conversation, conversation_id)
    newest = stored_messages(db, conversation_id)[-1]

    assert conversation.summary == "They asked twelve questions."
    assert conversation.summary_checkpoint_message_id == newest.id


def test_a_summarised_conversation_does_not_re_trigger_on_reload(session_factory, user):
    """
    The regression this class exists to prevent: reopening a long, already
    summarised conversation must not look like it is due for summarising.
    """

    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    for index in range(TRIGGER * 2):
        memory.add_message("user", f"question {index}")

    memory.update_summary("A long discussion.")

    reopened = memory_for(session_factory, conversation_id)

    assert len(reopened.messages) == 0
    assert len(reopened.messages) < TRIGGER
    assert reopened.get_summary() == "A long discussion."

    # Context for the prompt still comes from the full history.
    assert reopened.get_recent_messages(), "prompt context must survive the checkpoint"


def test_messages_after_the_checkpoint_are_counted_again(session_factory, user):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    for index in range(TRIGGER):
        memory.add_message("user", f"question {index}")

    memory.update_summary("A summary.")

    memory.add_message("user", "one more")
    memory.add_message("assistant", "one more answer")

    reopened = memory_for(session_factory, conversation_id)

    assert [message.content for message in reopened.messages] == [
        "one more",
        "one more answer",
    ]


def test_sources_attach_to_the_last_assistant_message(session_factory, user, db):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    memory.add_message("user", "What is the dose?")
    memory.add_message("assistant", "500 mg.")
    memory.add_message("user", "And for children?")
    memory.add_message("assistant", "Weight based.")

    memory.attach_sources([{"id": "doc_chunk_1", "filename": "bnf.pdf"}])

    db.expire_all()
    rows = stored_messages(db, conversation_id)

    assert rows[-1].sources == [{"id": "doc_chunk_1", "filename": "bnf.pdf"}]
    assert rows[1].sources is None, "the earlier answer keeps its own citations"


def test_attaching_sources_with_no_answer_yet_is_a_no_op(session_factory, user):
    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    memory.add_message("user", "What is the dose?")

    assert memory.attach_sources([{"id": "x"}]) is None


def test_adding_a_message_stamps_the_conversation(session_factory, user, db):
    """
    last_message_at is what the sidebar orders by, so a conversation that
    never updates it would sink to the bottom of the list.
    """

    conversation_id = make_conversation(session_factory, user.id)

    assert db.get(Conversation, conversation_id).last_message_at is None

    memory_for(session_factory, conversation_id).add_message("user", "Hello")

    db.expire_all()

    assert db.get(Conversation, conversation_id).last_message_at is not None


def test_memory_for_an_unknown_conversation_starts_empty(session_factory):
    """
    The query router creates the row before answering, but memory must not
    explode if it is built for an id that is not there yet.
    """

    memory = memory_for(session_factory, uuid.uuid4())

    assert memory.messages == []
    assert memory.get_summary() == ""


def test_the_store_hands_out_memory_per_conversation(session_factory, user):
    store = PersistentConversationStore(session_factory)
    conversation_id = make_conversation(session_factory, user.id)

    memory = store.get_memory(str(conversation_id))

    assert isinstance(memory, PersistentConversationMemory)
    assert memory.conversation_id == conversation_id


# ----------------------------------------------------------------------
# The trace an answer came from
# ----------------------------------------------------------------------


def test_an_answer_records_the_trace_that_produced_it(db, session_factory, user):
    """
    Taken from the ambient trace context, so no caller passes it and no
    signature changes. It is what turns "this answer was wrong" into a
    waterfall an admin can open.
    """

    from rag.observability import Tracer

    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    tracer = Tracer()

    with tracer.trace(trace_id="feedbeef") as trace:
        memory.add_message("assistant", "Take 500mg.")

        assert trace.trace_id == "feedbeef"

    (stored,) = stored_messages(db, conversation_id)

    assert stored.trace_id == "feedbeef"


def test_a_question_carries_no_trace(db, session_factory, user):
    """A trace explains an answer; the user's own question is not
    something the system produced."""

    from rag.observability import Tracer

    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    with Tracer().trace(trace_id="feedbeef"):
        memory.add_message("user", "What dose?")

    (stored,) = stored_messages(db, conversation_id)

    assert stored.trace_id is None


def test_an_answer_outside_a_trace_is_still_stored(db, session_factory, user):
    """
    A script, a test, or telemetry switched off entirely. The message is
    the point; the trace id is a convenience.
    """

    conversation_id = make_conversation(session_factory, user.id)
    memory = memory_for(session_factory, conversation_id)

    memory.add_message("assistant", "Take 500mg.")

    (stored,) = stored_messages(db, conversation_id)

    assert stored.trace_id is None
