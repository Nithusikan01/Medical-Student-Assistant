from unittest.mock import Mock

from rag_application.retrieval.retriever import Retriever
from rag_application.retrieval.schemas import RetrievedChunk


def test_retrieve_returns_retrieved_chunks():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.similarity_search.return_value = [
        {
            "id": "chunk_1",
            "score": 0.95,
            "metadata": {
                "original_text": "First chunk"
            }
        }
    ]

    retriever = Retriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model
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


def test_retrieve_calls_embedding_model():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [1, 2, 3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.similarity_search.return_value = []

    retriever = Retriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model
    )

    retriever.retrieve("test query")

    mock_embedding_model.encode.assert_called_once_with(
        "test query"
    )

def test_retrieve_calls_vector_store():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.similarity_search.return_value = []

    retriever = Retriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model
    )

    retriever.retrieve(
        query="test query",
        top_k=10
    )

    mock_vector_store.similarity_search.assert_called_once_with(
        query_vector=[0.1, 0.2, 0.3],
        top_k=10
    )


def test_retrieve_uses_text_when_original_text_missing():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.similarity_search.return_value = [
        {
            "id": "chunk_1",
            "score": 0.88,
            "metadata": {
                "text": "Fallback text"
            }
        }
    ]

    retriever = Retriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model
    )

    results = retriever.retrieve("query")

    assert results[0].text == "Fallback text"



def test_retrieve_returns_empty_list():

    mock_embedding_model = Mock()
    mock_vector_store = Mock()

    mock_embedding = Mock()
    mock_embedding.tolist.return_value = [0.1]

    mock_embedding_model.encode.return_value = mock_embedding

    mock_vector_store.similarity_search.return_value = []

    retriever = Retriever(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model
    )

    results = retriever.retrieve("query")

    assert results == []