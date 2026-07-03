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
        top_k=3,
        candidate_k=9,
    )

    mock_retriever.retrieve.assert_called_once_with(
        query="Who is Nithusikan?",
        top_k=9,
    )

    assert result == expected_chunks[:3]


def test_search_uses_reranker_when_available():
    mock_retriever = Mock()
    mock_reranker = Mock()

    candidates = [
        RetrievedChunk(id="chunk_1", score=0.2, text="Weak"),
        RetrievedChunk(id="chunk_2", score=0.9, text="Strong"),
    ]
    reranked = [candidates[1]]

    mock_retriever.retrieve.return_value = candidates
    mock_reranker.rerank.return_value = reranked

    service = QueryService(mock_retriever, reranker=mock_reranker)

    result = service.search("question", top_k=1, candidate_k=2)

    mock_reranker.rerank.assert_called_once_with(
        query="question",
        candidates=candidates,
        top_k=1,
    )
    assert result == reranked


def test_search_returns_empty_when_no_candidates():
    mock_retriever = Mock()
    mock_retriever.retrieve.return_value = []

    service = QueryService(mock_retriever)

    assert service.search("missing") == []
