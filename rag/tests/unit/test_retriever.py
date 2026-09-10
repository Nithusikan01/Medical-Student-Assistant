from unittest.mock import Mock

from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.retrieval.hybrid_retriever import HybridRetriever
from rag_application.retrieval.schemas import RetrievalMethod, RetrievedChunk
from tests.unit.helpers import make_retrieved_chunk, make_search_result


def test_dense_retrieve_returns_retrieved_chunks():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()
    mock_embedding_model.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_vector_store.query.return_value = [
        make_search_result("chunk_1", "First chunk", 0.95),
    ]

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    results = retriever.retrieve(
        query="Who is Nithusikan?",
        top_k=5,
    )

    assert len(results) == 1
    assert isinstance(results[0], RetrievedChunk)
    assert results[0].id == "chunk_1"
    assert results[0].score == 0.95
    assert results[0].text == "First chunk"
    assert results[0].metadata.filename == "doc.pdf"
    assert results[0].retrieval_method == RetrievalMethod.DENSE


def test_dense_retrieve_calls_embedding_model():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()
    mock_embedding_model.embed_query.return_value = [1, 2, 3]
    mock_vector_store.query.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    retriever.retrieve("test query")

    mock_embedding_model.embed_query.assert_called_once_with("test query")


def test_dense_retrieve_calls_vector_store():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()
    mock_embedding_model.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_vector_store.query.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    retriever.retrieve(
        query="test query",
        top_k=10,
    )

    mock_vector_store.query.assert_called_once_with(
        embedding=[0.1, 0.2, 0.3],
        top_k=10,
        filters=None,
    )


def test_dense_retrieve_returns_empty_list():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()
    mock_embedding_model.embed_query.return_value = [0.1]
    mock_vector_store.query.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    assert retriever.retrieve("query") == []


def test_dense_retrieve_skips_matches_without_text_metadata():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()
    mock_embedding_model.embed_query.return_value = [0.1]

    result = make_search_result("chunk_without_text", "Missing", 0.5)
    result.metadata.text = None
    mock_vector_store.query.return_value = [result]

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    assert retriever.retrieve("query") == []


def test_hybrid_retriever_fuses_dense_and_bm25_results():
    dense_retriever = Mock()
    bm25_retriever = Mock()
    shared = make_retrieved_chunk("shared", "Appears in both rankings", 0.8)
    dense_only = make_retrieved_chunk("dense", "Dense only", 0.7)
    bm25_only = make_retrieved_chunk("bm25", "BM25 only", 0.6)
    dense_retriever.retrieve.return_value = [shared, dense_only]
    bm25_retriever.retrieve.return_value = [shared, bm25_only]

    retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
        rrf_k=60,
    )

    results = retriever.retrieve("query", top_k=2)

    assert [result.id for result in results] == ["shared", "dense"]
    assert results[0].retrieval_method == RetrievalMethod.HYBRID
    assert results[0].score > results[1].score


def test_hybrid_retriever_returns_empty_when_sources_are_empty():
    dense_retriever = Mock()
    bm25_retriever = Mock()
    dense_retriever.retrieve.return_value = []
    bm25_retriever.retrieve.return_value = []

    retriever = HybridRetriever(dense_retriever, bm25_retriever)

    assert retriever.retrieve("query") == []
