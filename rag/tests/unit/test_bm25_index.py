import pytest

pytest.importorskip("rank_bm25")

from rag.indexes.bm25_index import BM25Index
from tests.unit.helpers import make_chunk


def test_empty_bm25_index_returns_no_results():
    index = BM25Index(documents=[])

    assert index.is_empty()
    assert index.search("anything") == []


def test_bm25_index_returns_matching_chunks():
    chunks = [
        make_chunk(0, "hybrid retrieval uses lexical search"),
        make_chunk(1, "semantic vectors answer similar meaning"),
        make_chunk(2, "reranking improves retrieved context"),
    ]
    index = BM25Index(documents=chunks)

    results = index.search("lexical", top_k=1)

    assert len(results) == 1
    assert results[0][0] == chunks[0]
    assert results[0][1] > 0


def test_punctuation_does_not_stop_a_query_term_matching():
    chunks = [
        make_chunk(0, "Sepsis is a dysregulated host response."),
        make_chunk(1, "Asthma is a chronic airway disease."),
        make_chunk(2, "Heart failure reduces cardiac output."),
    ]
    index = BM25Index(documents=chunks)

    results = index.search("What is sepsis?", top_k=1)

    assert [chunk for chunk, _ in results] == [chunks[0]]


def test_search_returns_the_top_k_in_score_order():
    chunks = [
        make_chunk(0, "insulin"),
        make_chunk(1, "insulin insulin glucagon"),
        make_chunk(2, "glucagon"),
        make_chunk(3, "cortisol"),
        make_chunk(4, "thyroxine"),
    ]
    index = BM25Index(documents=chunks)

    results = index.search("insulin", top_k=2)
    scores = [score for _, score in results]

    assert {chunk.chunk_index for chunk, _ in results} == {0, 1}
    assert scores == sorted(scores, reverse=True)


def test_a_query_with_no_word_characters_returns_nothing():
    index = BM25Index(documents=[make_chunk(0, "insulin")])

    assert index.search("???") == []
