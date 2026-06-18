from rag_application.ingestion.chunker import TextChunker
import pytest

def test_chunk_pages():
    pages = [
        "Hello world " * 100
    ]

    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    chunks = chunker.chunk(pages)

    assert len(chunks) > 1


def test_empty_pages():
    with pytest.raises(ValueError):
        chunker = TextChunker()
        chunker.chunk([])
        
