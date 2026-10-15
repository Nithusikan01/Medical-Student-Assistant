from unittest.mock import MagicMock

from rag.vectorstore.pinecone_store import VectorStore
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


def _store_with_client(client, dimension=1024):
    from rag.config.component_configs import PineconeConfig
    from rag.vectorstore.pinecone_store import PineconeVectorStore

    return PineconeVectorStore(
        PineconeConfig(api_key="k", index_name="idx", cloud="gcp", region="eu"),
        dimension=dimension,
        client=client,
    )


def test_constructing_the_store_does_not_create_an_index():
    client = MagicMock()

    _store_with_client(client)

    client.create_index.assert_not_called()
    client.has_index.assert_not_called()


def test_ensure_index_creates_a_missing_index_where_configured():
    client = MagicMock()
    client.has_index.return_value = False

    _store_with_client(client, dimension=384).ensure_index()

    kwargs = client.create_index.call_args.kwargs
    assert kwargs["dimension"] == 384
    assert kwargs["spec"].cloud == "gcp"
    assert kwargs["spec"].region == "eu"


def test_ensure_index_rejects_an_index_of_the_wrong_dimension():
    import pytest

    from rag.utils.exceptions import VectorStoreError

    client = MagicMock()
    client.has_index.return_value = True
    client.describe_index.return_value.dimension = 384

    with pytest.raises(VectorStoreError, match="dimension 384"):
        _store_with_client(client, dimension=1024).ensure_index()


def test_the_index_is_connected_on_first_use_not_at_construction():
    client = MagicMock()

    store = _store_with_client(client)

    client.Index.assert_not_called()

    store.count()

    client.Index.assert_called_once_with("idx")
