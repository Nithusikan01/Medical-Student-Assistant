from unittest.mock import Mock

from rag.retrieval.query_service import QueryService
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


def test_engine_components_satisfy_their_protocols_by_shape():
    from unittest.mock import MagicMock

    from rag.config.component_configs import PineconeConfig
    from rag.indexes.bm25_index import BM25Index
    from rag.rerankers.base import BaseReranker
    from rag.rerankers.fallback_reranker import FallbackReranker
    from rag.rerankers.gemini_reranker import GeminiReranker
    from rag.retrieval.base import BaseRetriever
    from rag.retrieval.bm25_retriever import BM25Retriever
    from rag.retrieval.dense_retriever import DenseRetriever
    from rag.retrieval.hybrid_retriever import HybridRetriever
    from rag.vectorstore.base import IdListingVectorStore, VectorStoreInterface
    from rag.vectorstore.pinecone_store import PineconeVectorStore

    store = PineconeVectorStore(
        PineconeConfig(api_key="k", index_name="i"), dimension=2, client=MagicMock()
    )
    dense = DenseRetriever(store, MagicMock())
    bm25 = BM25Retriever(BM25Index([]))

    assert isinstance(store, VectorStoreInterface)
    assert isinstance(store, IdListingVectorStore)
    assert all(
        isinstance(r, BaseRetriever)
        for r in (dense, bm25, HybridRetriever(dense, bm25))
    )

    gemini = GeminiReranker(MagicMock())
    assert isinstance(FallbackReranker(gemini, gemini), BaseReranker)


def test_a_store_without_list_ids_is_not_an_id_listing_store():
    from rag.vectorstore.base import IdListingVectorStore, VectorStoreInterface

    class MinimalStore:
        def upsert(self, records):
            return 0

        def query(self, embedding, top_k=5, filters=None):
            return []

        def delete(self, ids):
            return 0

        def count(self):
            return 0

    assert isinstance(MinimalStore(), VectorStoreInterface)
    assert not isinstance(MinimalStore(), IdListingVectorStore)
