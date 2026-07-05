from unittest.mock import Mock

from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.retrieval.hybrid_retriever import HybridRetriever
from rag_application.retrieval.schemas import RetrievedChunk


def test_retrieve_returns_retrieved_chunks():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.retrieve_vectors.return_value = [
        {
            "id": "chunk_1",
            "score": 0.95,
            "metadata": {
                "original_text": "First chunk",
                "source": "cv.pdf",
            },
        }
    ]

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    results = retriever.retrieve(
        query="Who is Nithusikan?",
        top_k=5
    )

    assert len(results) == 1

    assert isinstance(
        results[0],
        RetrievedChunk
    )

    assert results[0].id == "chunk_1"
    assert results[0].score == 0.95
    assert results[0].text == "First chunk"
    assert results[0].metadata == {"source": "cv.pdf"}
    assert results[0].retrieval_method == "dense"


def test_retrieve_calls_embedding_model():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [1, 2, 3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.retrieve_vectors.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    retriever.retrieve("test query")

    mock_embedding_model.encode.assert_called_once_with(
        "test query",
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


def test_retrieve_calls_vector_store():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.retrieve_vectors.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    retriever.retrieve(
        query="test query",
        top_k=10
    )

    mock_vector_store.retrieve_vectors.assert_called_once_with(
        query_vector=[0.1, 0.2, 0.3],
        top_k=10,
    )


def test_retrieve_uses_text_when_original_text_missing():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.retrieve_vectors.return_value = [
        {
            "id": "chunk_1",
            "score": 0.88,
            "metadata": {
                "text": "Fallback text",
            },
        }
    ]

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    results = retriever.retrieve("query")

    assert results[0].text == "Fallback text"
    assert "text" not in results[0].metadata

def test_retrieve_returns_empty_list():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.retrieve_vectors.return_value = []

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    results = retriever.retrieve("query")

    assert results == []


def test_retrieve_skips_matches_without_text_metadata():
    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1]

    mock_embedding_model.encode.return_value = mock_embedding
    mock_vector_store.retrieve_vectors.return_value = [
        {
            "id": "chunk_without_text",
            "score": 0.5,
            "metadata": {},
        }
    ]

    retriever = DenseRetriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
    )

    assert retriever.retrieve("query") == []


def test_hybrid_retriever_fuses_dense_and_bm25_results():
    dense_retriever = Mock()
    bm25_retriever = Mock()

    shared = RetrievedChunk(
        id="shared",
        score=0.8,
        text="Appears in both rankings",
        retrieval_method="dense",
    )
    dense_only = RetrievedChunk(id="dense", score=0.7, text="Dense only")
    bm25_only = RetrievedChunk(id="bm25", score=0.6, text="BM25 only")

    dense_retriever.retrieve.return_value = [shared, dense_only]
    bm25_retriever.retrieve.return_value = [shared, bm25_only]

    retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
        rrf_k=60,
    )

    results = retriever.retrieve("query", top_k=2)

    assert [result.id for result in results] == ["shared", "dense"]
    assert results[0].retrieval_method == "hybrid"
    assert results[0].score > results[1].score


def test_hybrid_retriever_returns_empty_when_sources_are_empty():
    dense_retriever = Mock()
    bm25_retriever = Mock()
    dense_retriever.retrieve.return_value = []
    bm25_retriever.retrieve.return_value = []

    retriever = HybridRetriever(dense_retriever, bm25_retriever)

    assert retriever.retrieve("query") == []
