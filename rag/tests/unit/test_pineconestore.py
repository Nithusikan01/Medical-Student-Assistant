from unittest.mock import MagicMock

from rag_application.vectorstore.pinecone_store import VectorStore
from tests.unit.helpers import make_vector_record


def test_pinecone_upsert():
    store = VectorStore.__new__(VectorStore)
    store.index = MagicMock()
    store.batch_size = 100

    total = store.upsert([make_vector_record()])

    assert total == 1
    store.index.upsert.assert_called_once()


def test_pinecone_query():
    store = VectorStore.__new__(VectorStore)
    store.index = MagicMock()

    match = MagicMock()
    match.id = "1"
    match.score = 0.9
    match.metadata = {
        "document_id": "doc",
        "filename": "doc.pdf",
        "source_path": "/tmp/doc.pdf",
        "text": "example",
        "chunk_index": 0,
    }
    response = MagicMock()
    response.matches = [match]
    store.index.query.return_value = response

    result = store.query([0.1, 0.2, 0.3], top_k=3)

    store.index.query.assert_called_once_with(
        vector=[0.1, 0.2, 0.3],
        top_k=3,
        filter=None,
        include_metadata=True,
    )
    assert result[0].id == "1"
    assert result[0].metadata.text == "example"
