from rag_application.ingestion.chunker import TextChunker
from rag_application.config.component_configs import ChunkingConfig
import pytest

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
    chunks = chunker.chunk(pages)

    assert len(chunks) > 1


def test_empty_pages():
    with pytest.raises(ValueError):
        chunker = TextChunker(
            ChunkingConfig(
                chunk_size=100,
                chunk_overlap=20
            )
        )
        chunker.chunk([])
