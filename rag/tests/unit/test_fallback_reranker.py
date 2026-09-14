from unittest.mock import Mock

from rag.rerankers.fallback_reranker import FallbackReranker
from tests.unit.helpers import make_retrieved_chunk


def _candidates():
    return [
        make_retrieved_chunk("chunk_1", "Weak", 0.2),
        make_retrieved_chunk("chunk_2", "Strong", 0.9),
    ]


def test_uses_primary_result_when_it_succeeds():
    primary = Mock()
    fallback = Mock()
    candidates = _candidates()
    primary.rerank.return_value = [candidates[1]]

    reranker = FallbackReranker(primary=primary, fallback=fallback)

    result = reranker.rerank("query", candidates, top_k=1)

    assert result == [candidates[1]]
    fallback.rerank.assert_not_called()


def test_uses_fallback_when_primary_raises():
    primary = Mock()
    fallback = Mock()
    candidates = _candidates()
    primary.rerank.side_effect = RuntimeError("hosted rerank unavailable")
    fallback.rerank.return_value = [candidates[0]]

    reranker = FallbackReranker(primary=primary, fallback=fallback)

    result = reranker.rerank("query", candidates, top_k=1)

    assert result == [candidates[0]]
    fallback.rerank.assert_called_once_with("query", candidates, 1)


def test_returns_retrieval_order_when_both_fail():
    primary = Mock()
    fallback = Mock()
    candidates = _candidates()
    primary.rerank.side_effect = RuntimeError("hosted rerank unavailable")
    fallback.rerank.side_effect = ValueError("gemini reranker failed")

    reranker = FallbackReranker(primary=primary, fallback=fallback)

    result = reranker.rerank("query", candidates, top_k=1)

    assert result == candidates[:1]


def test_returns_empty_for_no_candidates():
    primary = Mock()
    fallback = Mock()

    reranker = FallbackReranker(primary=primary, fallback=fallback)

    assert reranker.rerank("query", [], top_k=3) == []
    primary.rerank.assert_not_called()
    fallback.rerank.assert_not_called()
