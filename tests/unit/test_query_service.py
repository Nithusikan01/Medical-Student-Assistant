from unittest.mock import Mock

from rag_application.retrieval.query_service import QueryService
from rag_application.retrieval.schemas import RetrievedChunk


def test_search_calls_retriever():
    mock_retriever = Mock()

    expected_chunks = [
        RetrievedChunk(
            id="chunk_1",
            score=0.90,
            text="Test text"
        )
    ]

    mock_retriever.retrieve.return_value = expected_chunks

    service = QueryService(mock_retriever)

    result = service.search(
        query="Who is Nithusikan?",
        top_k=3
    )

    mock_retriever.retrieve.assert_called_once_with(
        query="Who is Nithusikan?",
        top_k=3
    )

    assert result == expected_chunks