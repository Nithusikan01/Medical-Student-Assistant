import pytest
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.ingestion.schemas import DocumentChunk


def make_chunk(index: int, text: str) -> DocumentChunk:
    return DocumentChunk(
        id=f"chunk_{index}",
        text=text,
        source="test_source",
        chunk_index=index,
    )


def test_prepare_basic_output():
    processor = VectorDataProcessor()

    vectors = [[0.1, 0.2], [0.3, 0.4]]
    chunks = [make_chunk(0, "chunk one"), make_chunk(1, "chunk two")]

    result = processor.prepare(vectors, chunks)

    assert isinstance(result, list)
    assert len(result) == 2

    for i, item in enumerate(result):
        assert "id" in item
        assert "vector" in item
        assert "metadata" in item

        assert item["id"] == f"chunk_{i}"
        assert item["vector"] == vectors[i]
        assert item["metadata"]["original_text"] == chunks[i].text
        assert item["metadata"]["chunk_id"] == i
        assert item["metadata"]["source"] == "test_source"
        assert "timestamp" in item["metadata"]


def test_vector_chunk_length_mismatch():
    processor = VectorDataProcessor()

    vectors = [[0.1, 0.2]]
    chunks = [make_chunk(0, "chunk1"), make_chunk(1, "chunk2")]

    with pytest.raises(ValueError, match="Mismatch between vectors and chunks"):
        processor.prepare(vectors, chunks)


def test_timestamp_exists_and_is_integer():
    processor = VectorDataProcessor()

    vectors = [[0.1]]
    chunks = [make_chunk(0, "test")]

    result = processor.prepare(vectors, chunks)

    ts = result[0]["metadata"]["timestamp"]

    assert isinstance(ts, int)
    assert ts > 0
