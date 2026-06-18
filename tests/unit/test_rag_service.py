from unittest.mock import Mock

from rag_application.llm.schemas import LLMResponse
from rag_application.retrieval.schemas import RetrievedChunk
from rag_application.services.rag_service import (
    RAGService,
)


def test_answer_returns_generated_response():

    mock_retriever = Mock()
    mock_generator = Mock()

    mock_retriever.retrieve.return_value = [
        RetrievedChunk(
            id="1",
            score=0.9,
            text="Nithusikan is a student."
        )
    ]

    mock_generator.generate.return_value = (
        LLMResponse(
            text="Generated answer"
        )
    )

    service = RAGService(
        retriever=mock_retriever,
        generator=mock_generator
    )

    answer = service.answer(
        "Who is Nithusikan?"
    )

    assert answer == "Generated answer"

def test_answer_returns_fallback_when_no_chunks():

    mock_retriever = Mock()
    mock_generator = Mock()

    mock_retriever.retrieve.return_value = []

    service = RAGService(
        retriever=mock_retriever,
        generator=mock_generator
    )

    answer = service.answer(
        "Unknown question"
    )

    assert (
        answer
        == "I don't know based on the provided document."
    )

def test_answer_calls_retriever():

    mock_retriever = Mock()
    mock_generator = Mock()

    mock_retriever.retrieve.return_value = [
        RetrievedChunk(
            id="1",
            score=0.9,
            text="Test"
        )
    ]

    mock_generator.generate.return_value = (
        LLMResponse(
            text="Answer"
        )
    )

    service = RAGService(
        retriever=mock_retriever,
        generator=mock_generator
    )

    service.answer(
        "question",
        top_k=10
    )

    mock_retriever.retrieve.assert_called_once_with(
        query="question",
        top_k=10
    )

def test_answer_calls_generator():

    mock_retriever = Mock()
    mock_generator = Mock()

    mock_retriever.retrieve.return_value = [
        RetrievedChunk(
            id="1",
            score=0.9,
            text="Test context"
        )
    ]

    mock_generator.generate.return_value = (
        LLMResponse(
            text="Answer"
        )
    )

    service = RAGService(
        retriever=mock_retriever,
        generator=mock_generator
    )

    service.answer(
        "question"
    )

    assert (
        mock_generator.generate.call_count
        == 1
    )