from rag.ingestion.processor import VectorDataProcessor
from rag.vectorstore.schemas import VectorRecord
from tests.unit.helpers import make_embedded_chunk


def test_prepare_basic_output():
    processor = VectorDataProcessor()
    embedded_chunks = [
        make_embedded_chunk(0, "chunk one", [0.1, 0.2]),
        make_embedded_chunk(1, "chunk two", [0.3, 0.4]),
    ]

    result = processor.prepare(embedded_chunks)

    assert all(isinstance(item, VectorRecord) for item in result)
    assert result[0].id == "doc_chunk_0"
    assert result[0].values == [0.1, 0.2]
    assert result[0].metadata.text == "chunk one"
    assert result[0].metadata.filename == "doc.pdf"


def test_prepare_empty_input():
    assert VectorDataProcessor().prepare([]) == []
