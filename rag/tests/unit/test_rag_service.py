from unittest.mock import Mock

from rag.cache.semantic_cache import InMemorySemanticCache
from rag.config.component_configs import CacheConfig
from rag.llm.schemas import LLMResponse
from rag.services.history_aware_rag_service import HistoryAwareRAGService
from tests.unit.helpers import make_retrieved_chunk


def build_cache(**overrides) -> InMemorySemanticCache:
    """
    The real cache, with the semantic tier off.

    Off because matching by meaning needs an embedder, and these tests are
    about what the service does with a hit - not about how one is found.
    test_response_cache.py covers the finding.
    """

    return InMemorySemanticCache(CacheConfig(semantic_enabled=False, **overrides))


def build_service(
    *,
    chunks=None,
    generated_text="Generated answer",
    response_cache=None,
    has_context=True,
):
    mock_query_service = Mock()
    mock_generator = Mock()
    mock_session_manager = Mock()
    mock_query_rewriter = Mock()
    mock_summarizer = Mock()
    mock_memory = Mock()

    # With no summary and no earlier turns the service treats this as an
    # opening question: it skips the rewriter, and the answer is eligible
    # for caching because nothing conversational went into the prompt.
    mock_memory.get_summary.return_value = "summary" if has_context else ""
    mock_memory.get_recent_messages.return_value = []
    mock_memory.messages = []
    mock_session_manager.get_memory.return_value = mock_memory
    mock_query_rewriter.rewrite.return_value = "rewritten question"

    if chunks is None:
        chunks = [
            make_retrieved_chunk(
                chunk_id="1",
                text="Nithusikan is a student.",
            )
        ]

    mock_query_service.search.return_value = chunks
    mock_generator.generate.return_value = LLMResponse(text=generated_text)
    mock_summarizer.summarize.return_value = "new summary"

    service = HistoryAwareRAGService(
        query_service=mock_query_service,
        generator=mock_generator,
        session_manager=mock_session_manager,
        query_rewriter=mock_query_rewriter,
        summarizer=mock_summarizer,
        response_cache=response_cache,
    )

    return (
        service,
        mock_query_service,
        mock_generator,
        mock_session_manager,
        mock_query_rewriter,
        mock_summarizer,
        mock_memory,
    )


def test_answer_returns_generated_response():
    service, *_ = build_service(generated_text="Generated answer")

    answer = service.answer(
        conversation_id="conversation_1",
        question="Who is Nithusikan?",
    )

    assert answer == "Generated answer"


def test_answer_returns_fallback_when_no_chunks():
    service, _, mock_generator, *_ = build_service(chunks=[])

    answer, sources = service.answer_with_sources(
        conversation_id="conversation_1",
        question="Unknown question",
    )

    assert answer == "I couldn't find relevant information in the documents."
    assert sources == []
    mock_generator.generate.assert_not_called()


def test_answer_calls_query_service_with_rewritten_query():
    (
        service,
        mock_query_service,
        _,
        _,
        mock_query_rewriter,
        _,
        mock_memory,
    ) = build_service(generated_text="Answer")

    service.answer(
        conversation_id="conversation_1",
        question="question",
        top_k=10,
    )

    mock_query_rewriter.rewrite.assert_called_once_with(
        query="question",
        summary="summary",
        recent_messages=[],
    )
    mock_query_service.search.assert_called_once_with(
        query="rewritten question",
        top_k=10,
        candidate_k=30,
        use_reranker=True,
        query_embedding=None,
    )
    mock_memory.add_message.assert_any_call(
        role="user",
        content="question",
    )
    mock_memory.add_message.assert_any_call(
        role="assistant",
        content="Answer",
    )


def test_answer_calls_generator():
    service, _, mock_generator, *_ = build_service(generated_text="Answer")

    service.answer(
        conversation_id="conversation_1",
        question="question",
    )

    assert mock_generator.generate.call_count == 1


def test_answer_with_sources_uses_override_generator_when_given():
    service, _, mock_generator, *_ = build_service(generated_text="Default answer")

    override_generator = Mock()
    override_generator.generate.return_value = LLMResponse(text="Override answer")

    answer, _ = service.answer_with_sources(
        conversation_id="conversation_1",
        question="question",
        generator=override_generator,
    )

    assert answer == "Override answer"
    override_generator.generate.assert_called_once()
    mock_generator.generate.assert_not_called()


def test_answer_updates_summary_after_trigger():
    service, *_, mock_summarizer, mock_memory = build_service(
        generated_text="Answer",
    )
    mock_memory.messages = [Mock() for _ in range(service.SUMMARY_TRIGGER)]

    service.answer(
        conversation_id="conversation_1",
        question="question",
    )

    mock_summarizer.summarize.assert_called_once_with(mock_memory)
    mock_memory.update_summary.assert_called_once_with("new summary")


# ----------------------------------------------------------------------
# The response cache
# ----------------------------------------------------------------------


def test_an_opening_question_is_not_rewritten():
    """
    Nothing to resolve means nothing to rewrite, and an LLM call saved on
    every new conversation.
    """

    (
        service,
        mock_query_service,
        _,
        _,
        mock_query_rewriter,
        *_,
    ) = build_service(has_context=False)

    service.answer(conversation_id="conversation_1", question="What is the dose?")

    mock_query_rewriter.rewrite.assert_not_called()

    # Retrieval ran on the question exactly as it was asked.
    assert mock_query_service.search.call_args.kwargs["query"] == "What is the dose?"


def test_a_repeated_question_skips_retrieval_and_generation():
    service, mock_query_service, mock_generator, *_ = build_service(
        generated_text="Answer",
        response_cache=build_cache(),
        has_context=False,
    )

    first, first_sources = service.answer_with_sources(
        conversation_id="conversation_1",
        question="What is the dose?",
    )

    mock_query_service.search.reset_mock()
    mock_generator.generate.reset_mock()

    second, second_sources = service.answer_with_sources(
        conversation_id="conversation_2",
        question="what is the dose",
    )

    assert second == first
    assert second_sources == first_sources

    # The point of the whole thing: neither the vector store nor the LLM
    # was asked a second time.
    mock_query_service.search.assert_not_called()
    mock_generator.generate.assert_not_called()


def test_a_cached_answer_is_still_written_to_the_conversation():
    """
    A hit skips the work, never the record of it. Leaving the assistant
    turn out would show the user an answer the stored conversation does
    not contain.
    """

    service, *_, mock_memory = build_service(
        generated_text="Answer",
        response_cache=build_cache(),
        has_context=False,
    )

    service.answer(conversation_id="conversation_1", question="What is the dose?")

    mock_memory.add_message.reset_mock()

    service.answer(conversation_id="conversation_2", question="What is the dose?")

    mock_memory.add_message.assert_any_call(role="user", content="What is the dose?")
    mock_memory.add_message.assert_any_call(role="assistant", content="Answer")


def test_a_cached_answer_still_triggers_the_summary():
    service, _, _, _, _, mock_summarizer, mock_memory = build_service(
        generated_text="Answer",
        response_cache=build_cache(),
        has_context=False,
    )

    service.answer(conversation_id="conversation_1", question="What is the dose?")

    mock_memory.messages = [Mock() for _ in range(service.SUMMARY_TRIGGER)]
    mock_summarizer.summarize.reset_mock()

    service.answer(conversation_id="conversation_2", question="What is the dose?")

    mock_summarizer.summarize.assert_called_once_with(mock_memory)


def test_an_answer_written_with_conversation_context_is_not_cached():
    """
    Such an answer can refer back to the conversation it was written for
    ("as I said above"), and there is no way to tell from the text whether
    it did - so it is never handed to anyone else.
    """

    service, mock_query_service, mock_generator, *_ = build_service(
        generated_text="Answer",
        response_cache=build_cache(),
        has_context=True,
    )

    service.answer(conversation_id="conversation_1", question="question")

    mock_query_service.search.reset_mock()
    mock_generator.generate.reset_mock()

    service.answer(conversation_id="conversation_2", question="question")

    mock_query_service.search.assert_called_once()
    mock_generator.generate.assert_called_once()


def test_a_different_model_does_not_reuse_another_model_s_answer():
    service, mock_query_service, *_ = build_service(
        generated_text="Answer",
        response_cache=build_cache(),
        has_context=False,
    )

    service.answer(
        conversation_id="conversation_1",
        question="What is the dose?",
        model_id="gemini-flash",
    )

    mock_query_service.search.reset_mock()

    service.answer(
        conversation_id="conversation_2",
        question="What is the dose?",
        model_id="groq-gpt-oss-20b",
    )

    mock_query_service.search.assert_called_once()


def test_no_cache_means_no_change_in_behaviour():
    """
    The default. Every question does the full pipeline, as it did before
    there was a cache at all.
    """

    service, mock_query_service, mock_generator, *_ = build_service(
        generated_text="Answer",
        has_context=False,
    )

    service.answer(conversation_id="conversation_1", question="What is the dose?")
    service.answer(conversation_id="conversation_2", question="What is the dose?")

    assert mock_query_service.search.call_count == 2
    assert mock_generator.generate.call_count == 2
