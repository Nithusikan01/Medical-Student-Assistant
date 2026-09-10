from unittest.mock import Mock

import pytest

from rag_application.utils.exceptions import VectorStoreError
from rag_application.vectorstore.pinecone_store import (
    DELETE_BATCH_SIZE,
    PineconeVectorStore,
)


def make_store(index: Mock) -> PineconeVectorStore:
    store = PineconeVectorStore.__new__(PineconeVectorStore)
    store.index = index
    store.index_name = "test-index"
    store.batch_size = 100
    return store


def test_delete_batches_ids_at_the_pinecone_limit():
    index = Mock()
    store = make_store(index)

    ids = [f"doc_chunk_{i}" for i in range(DELETE_BATCH_SIZE + 250)]

    assert store.delete(ids) == len(ids)

    assert index.delete.call_count == 2
    first, second = index.delete.call_args_list
    assert len(first.kwargs["ids"]) == DELETE_BATCH_SIZE
    assert len(second.kwargs["ids"]) == 250
    # Every id is deleted exactly once.
    assert first.kwargs["ids"] + second.kwargs["ids"] == ids


def test_delete_of_nothing_makes_no_call():
    index = Mock()
    store = make_store(index)

    assert store.delete([]) == 0
    index.delete.assert_not_called()


def test_delete_wraps_failures():
    index = Mock()
    index.delete.side_effect = RuntimeError("pinecone is down")
    store = make_store(index)

    with pytest.raises(VectorStoreError):
        store.delete(["doc_chunk_0"])


def test_list_ids_follows_pagination():
    index = Mock()
    index.list.return_value = iter(
        [
            ["doc_chunk_0", "doc_chunk_1"],
            ["doc_chunk_2"],
        ]
    )
    store = make_store(index)

    assert list(store.list_ids("doc_chunk_")) == [
        "doc_chunk_0",
        "doc_chunk_1",
        "doc_chunk_2",
    ]
    index.list.assert_called_once_with(prefix="doc_chunk_")


def test_list_ids_accepts_objects_with_an_id_attribute():
    index = Mock()
    index.list.return_value = iter([[Mock(id="doc_chunk_0")]])
    store = make_store(index)

    assert list(store.list_ids("doc_chunk_")) == ["doc_chunk_0"]
