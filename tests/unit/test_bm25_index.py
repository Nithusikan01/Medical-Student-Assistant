import pytest

pytest.importorskip("rank_bm25")

from rag_application.indexes.bm25_index import BM25Index

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
