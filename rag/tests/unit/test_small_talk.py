import pytest

from rag.config.component_configs import SmallTalkConfig
from rag.conversation.small_talk import (
    SmallTalkIntent,
    SmallTalkResponder,
    normalise,
)


@pytest.fixture
def responder() -> SmallTalkResponder:
    return SmallTalkResponder()


# ----------------------------------------------------------------------
# What must be recognised
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Hi", SmallTalkIntent.GREETING),
        ("hi!", SmallTalkIntent.GREETING),
        ("Hiii", SmallTalkIntent.GREETING),
        ("Hello", SmallTalkIntent.GREETING),
        ("hello there", SmallTalkIntent.GREETING),
        ("Hey!!", SmallTalkIntent.GREETING),
        ("hey there", SmallTalkIntent.GREETING),
        ("Good morning", SmallTalkIntent.GREETING),
        ("good evening!", SmallTalkIntent.GREETING),
        ("Good afternoon Anamnesis", SmallTalkIntent.GREETING),
        ("greetings", SmallTalkIntent.GREETING),
        ("yo", SmallTalkIntent.GREETING),
        ("  HELLO  ", SmallTalkIntent.GREETING),
        ("how are you?", SmallTalkIntent.CHECK_IN),
        ("hi, how are you doing?", SmallTalkIntent.CHECK_IN),
        ("what's up", SmallTalkIntent.CHECK_IN),
        ("are you there?", SmallTalkIntent.CHECK_IN),
        ("who are you?", SmallTalkIntent.IDENTITY),
        ("what can you do", SmallTalkIntent.IDENTITY),
        ("how can you help me?", SmallTalkIntent.IDENTITY),
        ("what is this?", SmallTalkIntent.IDENTITY),
        ("help", SmallTalkIntent.IDENTITY),
        ("thanks", SmallTalkIntent.THANKS),
        ("Thank you!", SmallTalkIntent.THANKS),
        ("thanks a lot", SmallTalkIntent.THANKS),
        ("ok thanks", SmallTalkIntent.THANKS),
        ("great, thank you so much", SmallTalkIntent.THANKS),
        ("bye", SmallTalkIntent.FAREWELL),
        ("goodbye!", SmallTalkIntent.FAREWELL),
        ("thanks, bye", SmallTalkIntent.FAREWELL),
        ("good night", SmallTalkIntent.FAREWELL),
        ("see you later", SmallTalkIntent.FAREWELL),
        ("ok", SmallTalkIntent.ACKNOWLEDGEMENT),
        ("got it", SmallTalkIntent.ACKNOWLEDGEMENT),
        ("makes sense", SmallTalkIntent.ACKNOWLEDGEMENT),
    ],
)
def test_conversational_turns_are_recognised(responder, message, intent):
    reply = responder.reply_to(message)

    assert reply is not None
    assert reply.intent is intent
    assert reply.text.strip()


# ----------------------------------------------------------------------
# What must fall through
#
# The costly direction of a mistake: a swallowed question is answered
# with a canned greeting instead of from the corpus.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Hi, what is the pathophysiology of sepsis?",
        "hello, can you summarise chapter 3",
        "What are the signs of hypoglycaemia?",
        "thanks for the answer, but what does the guideline say about dosing?",
        "who is the author of the cardiology notes?",
        "what is this condition called when the heart rate exceeds 100 bpm",
        "how are cranial nerves numbered?",
        "how do you help a patient in anaphylaxis?",
        "good sources for pharmacology",
        "ok so what about the second one",
        "help me understand the Krebs cycle",
    ],
)
def test_real_questions_are_left_to_retrieval(responder, message):
    assert responder.reply_to(message) is None


def test_empty_message_is_not_small_talk(responder):
    assert responder.reply_to("   ") is None


# ----------------------------------------------------------------------
# The replies themselves
# ----------------------------------------------------------------------


def test_greeting_introduces_the_assistant_by_name(responder):
    reply = responder.reply_to("hi")

    assert reply is not None
    assert "Anamnesis" in reply.text
    assert reply.text.startswith("Hello!")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("good morning", "Good morning!"),
        ("Good afternoon!", "Good afternoon!"),
        ("good evening there", "Good evening!"),
        ("hey", "Hello!"),
    ],
)
def test_a_time_of_day_greeting_is_mirrored(responder, message, expected):
    reply = responder.reply_to(message)

    assert reply is not None
    assert reply.text.startswith(expected)


def test_thanks_does_not_re_introduce_the_assistant(responder):
    reply = responder.reply_to("thank you")

    assert reply is not None
    assert "Anamnesis" not in reply.text


def test_the_assistant_name_and_description_are_configurable():
    responder = SmallTalkResponder(
        SmallTalkConfig(
            assistant_name="Hippocrates",
            corpus_description="guide to the second-year reading list",
        )
    )

    reply = responder.reply_to("hello")

    assert reply is not None
    assert "Hippocrates" in reply.text
    assert "second-year reading list" in reply.text
    assert "Anamnesis" not in reply.text


def test_disabled_responder_recognises_nothing():
    responder = SmallTalkResponder(SmallTalkConfig(enabled=False))

    assert responder.reply_to("hello") is None


# ----------------------------------------------------------------------
# Normalisation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hi!!!", "hi"),
        ("  Good   Morning. ", "good morning"),
        ("what's up?", "whats up"),
        ("Thank you :)", "thank you"),
        ("HELLO", "hello"),
    ],
)
def test_normalise(raw, expected):
    assert normalise(raw) == expected
