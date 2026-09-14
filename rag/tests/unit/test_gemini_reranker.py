import pytest

from rag.rerankers.gemini_reranker import GeminiReranker
from tests.unit.helpers import make_retrieved_chunk


class FakeGenerator:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, prompt: str):
        class _Response:
            text = self._text

        return _Response()


def _candidates():
    return [
        make_retrieved_chunk("chunk_0", "Weak match", 0.1),
        make_retrieved_chunk("chunk_1", "Strong match", 0.2),
        make_retrieved_chunk("chunk_2", "Medium match", 0.3),
    ]


def test_rerank_orders_by_returned_ranking():
    generator = FakeGenerator(
        '[{"index": 1, "score": 0.9}, {"index": 2, "score": 0.5}]'
    )
    reranker = GeminiReranker(generator)

    results = reranker.rerank("query", _candidates(), top_k=2)

    assert [chunk.id for chunk in results] == ["chunk_1", "chunk_2"]
    assert results[0].rerank_score == 0.9
    assert results[0].rank == 1


def test_rerank_strips_markdown_fence():
    generator = FakeGenerator('```json\n[{"index": 0, "score": 0.8}]\n```')
    reranker = GeminiReranker(generator)

    results = reranker.rerank("query", _candidates(), top_k=1)

    assert [chunk.id for chunk in results] == ["chunk_0"]


def test_rerank_raises_on_malformed_json():
    generator = FakeGenerator("not json at all")
    reranker = GeminiReranker(generator)

    with pytest.raises(ValueError):
        reranker.rerank("query", _candidates(), top_k=2)


def test_rerank_ignores_out_of_range_and_duplicate_indices():
    generator = FakeGenerator(
        '[{"index": 5, "score": 0.9}, {"index": 1, "score": 0.7}, '
        '{"index": 1, "score": 0.6}]'
    )
    reranker = GeminiReranker(generator)

    results = reranker.rerank("query", _candidates(), top_k=5)

    assert [chunk.id for chunk in results] == ["chunk_1"]


def test_rerank_returns_empty_for_no_candidates():
    reranker = GeminiReranker(FakeGenerator("[]"))

    assert reranker.rerank("query", [], top_k=3) == []
