import pytest

from rag.config.settings import settings_from_mapping

REQUIRED = {
    "PINECONE_API_KEY": "test_api_key",
    "PINECONE_INDEX_NAME": "test_index_name",
    "GEMINI_API_KEY": "test_gemini_api_key",
}


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_each_required_value_is_enforced(missing):
    values = {key: value for key, value in REQUIRED.items() if key != missing}

    with pytest.raises(ValueError, match=missing):
        settings_from_mapping(values)


def test_required_values_are_read():
    settings = settings_from_mapping(REQUIRED)

    assert settings.pinecone_api_key == "test_api_key"
    assert settings.pinecone_index_name == "test_index_name"
    assert settings.gemini_api_key == "test_gemini_api_key"


def test_optional_values_are_parsed_from_strings():
    settings = settings_from_mapping(
        {
            **REQUIRED,
            "CANDIDATE_K": "12",
            "RESPONSE_CACHE_SIMILARITY_THRESHOLD": "0.9",
            "USE_HOSTED_INFERENCE": "false",
            "SMALL_TALK_ENABLED": "yes",
        }
    )

    assert settings.candidate_k == 12
    assert settings.response_cache_similarity_threshold == 0.9
    assert settings.use_hosted_inference is False
    assert settings.small_talk_enabled is True


def test_the_engine_does_not_read_the_process_environment(monkeypatch):
    monkeypatch.setenv("CANDIDATE_K", "99")

    assert settings_from_mapping(REQUIRED).candidate_k == 30


def test_the_assistant_introduces_itself_as_a_medical_study_assistant():
    from rag.conversation.small_talk import SmallTalkResponder

    settings = settings_from_mapping(REQUIRED)
    greeting = SmallTalkResponder(settings.small_talk_config()).reply_to("hi").text
    refusal = settings.scope_config().refusal_text

    for text in (greeting, refusal):
        assert "medical study assistant" in text
        assert "help medical students" in text
        assert "prepare for exams" in text


def test_the_refusal_names_the_subject_rather_than_your_course():
    """
    Students of other fields can register too, and would read "your
    course" as their own. The refusal says which subject it answers.
    """

    refusal = settings_from_mapping(REQUIRED).scope_config().refusal_text

    assert "I can only answer questions about medicine and the health sciences" in (
        refusal
    )
    assert "Please feel free to ask a medical question" in refusal
    assert "your course" not in refusal
    assert "your lecture notes" not in refusal


def test_the_refusal_follows_the_configured_identity():
    settings = settings_from_mapping(
        {
            **REQUIRED,
            "ASSISTANT_NAME": "Hippocrates",
            "ASSISTANT_DESCRIPTION": "nursing study assistant",
            "ASSISTANT_PURPOSE": "I help nursing students revise.",
        }
    )

    refusal = settings.scope_config().refusal_text

    assert (
        "I'm Hippocrates, your nursing study assistant. I help nursing students revise."
        in refusal
    )


def test_an_explicit_refusal_overrides_the_composed_one():
    settings = settings_from_mapping({**REQUIRED, "SCOPE_REFUSAL": "Not here."})

    assert settings.scope_config().refusal_text == "Not here."


def test_the_greeting_invites_medical_questions():
    """
    The greeting used to invite "anything from the course material", which
    a student of another field would read as their own course. It names the
    same subject the scope guard answers, with medical examples.
    """

    from rag.conversation.small_talk import SmallTalkResponder

    settings = settings_from_mapping(REQUIRED)
    greeting = SmallTalkResponder(settings.small_talk_config()).reply_to("hi").text

    assert "Ask me anything about medicine and the health sciences" in greeting
    assert "a topic for a medical exam" in greeting
    assert "anything from the course material" not in greeting


def test_the_greeting_follows_the_scope_subject():
    from rag.conversation.small_talk import SmallTalkResponder

    settings = settings_from_mapping({**REQUIRED, "SCOPE_SUBJECT": "nursing"})
    greeting = SmallTalkResponder(settings.small_talk_config()).reply_to("hi").text

    assert "Ask me anything about nursing from the class library" in greeting


def test_the_refusal_opens_with_an_apology():
    """It is the one reply that turns a student's request down."""

    refusal = settings_from_mapping(REQUIRED).scope_config().refusal_text

    assert refusal.startswith(
        "Apologies for the inconvenience - I'm not able to help with that question."
    )
