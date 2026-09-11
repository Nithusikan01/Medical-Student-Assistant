from unittest.mock import Mock, patch

from rag.config.component_configs import ChunkingConfig
from rag.ingestion.chunker import TextChunker
from rag.ingestion.schemas import DocumentChunk, LoadedDocument
from tests.unit.helpers import make_loaded_document


@patch("rag.ingestion.chunker._build_splitter")
def test_chunk_document(mock_build_splitter):
    splitter = Mock()
    splitter.split_text.return_value = [
        "Hello world",
        "second chunk",
    ]
    mock_build_splitter.return_value = splitter
    document = make_loaded_document("Hello world " * 100)
    chunker = TextChunker(
        ChunkingConfig(
            chunk_size=100,
            chunk_overlap=20,
        )
    )

    chunks = chunker.chunk(document)

    assert len(chunks) > 1
    assert all(isinstance(chunk, DocumentChunk) for chunk in chunks)
    assert chunks[0].id == "doc_chunk_0"
    assert chunks[0].metadata.filename == "doc.pdf"


@patch("rag.ingestion.chunker._build_splitter")
def test_empty_document_pages(mock_build_splitter):
    document = LoadedDocument(
        document_id="empty",
        filename="empty.pdf",
        source_path="/tmp/empty.pdf",
        pages=[],
    )
    chunker = TextChunker(
        ChunkingConfig(
            chunk_size=100,
            chunk_overlap=20,
        )
    )

    assert chunker.chunk(document) == []
