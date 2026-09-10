from unittest.mock import Mock

from rag_application.retrieval.query_service import QueryService

from tests.unit.helpers import make_retrieved_chunk


def test_search_calls_retriever():
    mock_retriever = Mock()
    expected_chunks = [
        make_retrieved_chunk("chunk_1", "Test text", 0.90),
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
        make_retrieved_chunk("chunk_1", "Weak", 0.2),
        make_retrieved_chunk("chunk_2", "Strong", 0.9),
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
