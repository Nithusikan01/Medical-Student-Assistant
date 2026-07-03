from unittest.mock import MagicMock

from rag_application.vectorstore.pinecone_store import VectorStore


def test_pinecone_store():

    store = VectorStore.__new__(VectorStore)

    store.index = MagicMock()

    vector_data = [
        {
            "id": "1",
            "vector": [0.1, 0.2, 0.3],
            "metadata": {"text": "example"}
        }
    ]
    
    store.store_vectors(vector_data)

    store.index.upsert.assert_called_once()

def test_retrieve_vectors():

    store = VectorStore.__new__(VectorStore)

    store.index = MagicMock()

    store.index.query.return_value = {
        "matches": [
            {
                "id": "1",
                "score": 0.9,
                "metadata": {"text": "example"},
            }
        ]
    }

    result = store.retrieve_vectors([0.1, 0.2, 0.3], top_k=3)

    store.index.query.assert_called_once_with(
        vector=[0.1, 0.2, 0.3],
        top_k=3,
        include_metadata=True,
    )
    assert result == store.index.query.return_value["matches"]
