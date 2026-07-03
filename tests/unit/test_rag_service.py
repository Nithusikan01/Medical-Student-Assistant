from unittest.mock import Mock

from rag_application.llm.schemas import LLMResponse
from rag_application.retrieval.schemas import RetrievedChunk
from rag_application.services.history_aware_rag_service import HistoryAwareRAGService


def build_service(
    *,
    chunks=None,
    generated_text="Generated answer",
):
    mock_query_service = Mock()
    mock_generator = Mock()
    mock_session_manager = Mock()
    mock_query_rewriter = Mock()
    mock_summarizer = Mock()
    mock_memory = Mock()

    mock_memory.get_summary.return_value = "summary"
    mock_memory.get_recent_messages.return_value = []
    mock_memory.messages = []

    mock_session_manager.get_memory.return_value = mock_memory
    mock_query_rewriter.rewrite.return_value = "rewritten question"
    if chunks is None:
        chunks = [
            RetrievedChunk(
                id="1",
                score=0.9,
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

    assert (
        answer
        == "I couldn't find relevant information in the documents."
    )
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
    )
    mock_memory.add_message.assert_any_call("user", "question")
    mock_memory.add_message.assert_any_call("assistant", "Answer")


def test_answer_calls_generator():
    service, _, mock_generator, *_ = build_service(generated_text="Answer")

    service.answer(
        conversation_id="conversation_1",
        question="question",
    )

    assert (
        mock_generator.generate.call_count
        == 1
    )


def test_answer_updates_summary_after_trigger():
    service, *_, mock_summarizer, mock_memory = build_service(generated_text="Answer")
    mock_memory.messages = [Mock() for _ in range(service.SUMMARY_TRIGGER)]

    service.answer(
        conversation_id="conversation_1",
        question="question",
    )

    mock_summarizer.summarize.assert_called_once_with(mock_memory)
    mock_memory.update_summary.assert_called_once_with("new summary")
