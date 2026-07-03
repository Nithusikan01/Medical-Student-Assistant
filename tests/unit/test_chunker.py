from rag_application.config.component_configs import ChunkingConfig
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.schemas import DocumentChunk


def test_chunk_pages():
    pages = [
        "Hello world " * 100
    ]

    chunker = TextChunker(
        ChunkingConfig(
            chunk_size=100,
            chunk_overlap=20
        )
    )
    chunks = chunker.chunk(pages, source="unit-test.txt")

    assert len(chunks) > 1
    assert all(isinstance(chunk, DocumentChunk) for chunk in chunks)
    assert chunks[0].id == "unit-test.txt_chunk_0"
    assert chunks[0].source == "unit-test.txt"


def test_empty_pages():
    chunker = TextChunker(
        ChunkingConfig(
            chunk_size=100,
            chunk_overlap=20
        )
    )

    assert chunker.chunk([], source="empty.txt") == []
