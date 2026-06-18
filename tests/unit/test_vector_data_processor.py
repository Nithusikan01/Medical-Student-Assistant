import pytest
from rag_application.ingestion.processor import VectorDataProcessor


def test_prepare_basic_output():
    processor = VectorDataProcessor()

    vectors = [[0.1, 0.2], [0.3, 0.4]]
    chunks = ["chunk one", "chunk two"]

    result = processor.prepare(vectors, chunks, source="test_source")

    assert isinstance(result, list)
    assert len(result) == 2

    for i, item in enumerate(result):
        assert "id" in item
        assert "vector" in item
        assert "metadata" in item

        assert item["id"] == f"test_source_chunk_{i}"
        assert item["vector"] == vectors[i]
        assert item["metadata"]["original_text"] == chunks[i]
        assert item["metadata"]["chunk_id"] == i
        assert item["metadata"]["source"] == "test_source"
        assert "timestamp" in item["metadata"]


def test_vector_chunk_length_mismatch():
    processor = VectorDataProcessor()

    vectors = [[0.1, 0.2]]
    chunks = ["chunk1", "chunk2"]

    with pytest.raises(ValueError, match="vectors and chunks length mismatch"):
        processor.prepare(vectors, chunks)


def test_page_numbers_added_correctly():
    processor = VectorDataProcessor()

    vectors = [[0.1], [0.2], [0.3]]
    chunks = ["a", "b", "c"]
    pages = [1, 2, 3]

    result = processor.prepare(vectors, chunks, page_numbers=pages)

    for i, item in enumerate(result):
        assert "page_number" in item["metadata"]
        assert item["metadata"]["page_number"] == pages[i]


def test_page_numbers_length_mismatch():
    processor = VectorDataProcessor()

    vectors = [[0.1], [0.2]]
    chunks = ["a", "b"]
    pages = [1]  # mismatch

    with pytest.raises(ValueError, match="page_numbers length mismatch"):
        processor.prepare(vectors, chunks, page_numbers=pages)


def test_source_default_value():
    processor = VectorDataProcessor()

    vectors = [[0.1]]
    chunks = ["test"]

    result = processor.prepare(vectors, chunks)

    assert result[0]["metadata"]["source"] == "unknown"
    assert result[0]["id"].startswith("unknown_chunk_")


def test_timestamp_exists_and_is_integer():
    processor = VectorDataProcessor()

    vectors = [[0.1]]
    chunks = ["test"]

    result = processor.prepare(vectors, chunks)

    ts = result[0]["metadata"]["timestamp"]

    assert isinstance(ts, int)
    assert ts > 0