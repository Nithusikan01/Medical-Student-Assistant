from pathlib import Path
from unittest.mock import Mock, patch

from rag.config.component_configs import ChunkingConfig
from rag.ingestion.chunker import TextChunker
from rag.ingestion.schemas import DocumentChunk, LoadedDocument, LoadedPage
from tests.unit.helpers import make_loaded_document

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


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


def test_chunker_splits_a_real_document():
    """
    The two tests above patch the splitter, so nothing checks that the real
    langchain splitter is wired up correctly. This one runs it for real
    against a text fixture - no network, no model weights.
    """

    text = (FIXTURES_DIR / "output.txt").read_text(encoding="utf-8")
    document = LoadedDocument(
        document_id="output",
        filename="output.txt",
        source_path=str(FIXTURES_DIR / "output.txt"),
        pages=[LoadedPage(page_number=1, text=text)],
    )

    chunks = TextChunker(ChunkingConfig(chunk_size=500, chunk_overlap=50)).chunk(
        document
    )

    assert len(chunks) > 1
    assert chunks[0].id == "output_chunk_0"
    assert chunks[0].metadata.filename == "output.txt"
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(chunk.metadata.chunk_size <= 500 for chunk in chunks)


def test_chunk_batches_split_pages_only_as_batches_are_pulled():
    from unittest.mock import MagicMock

    from rag.config.component_configs import ChunkingConfig
    from rag.ingestion.chunker import TextChunker
    from rag.ingestion.schemas import LoadedDocument, LoadedPage

    chunker = TextChunker(ChunkingConfig(chunk_size=500, chunk_overlap=0))
    chunker.splitter = MagicMock()
    chunker.splitter.split_text.side_effect = lambda text: [text]

    document = LoadedDocument(
        document_id="doc",
        filename="doc.pdf",
        source_path="/tmp/doc.pdf",
        pages=[LoadedPage(page_number=n, text=f"page {n}") for n in range(1, 6)],
    )

    batches = chunker.chunk_batches(document, batch_size=2)
    first = next(batches)

    assert [chunk.text for chunk in first] == ["page 1", "page 2"]
    assert chunker.splitter.split_text.call_count == 2

    rest = list(batches)

    assert [len(batch) for batch in rest] == [2, 1]
    assert [chunk.chunk_index for batch in [first, *rest] for chunk in batch] == [
        0,
        1,
        2,
        3,
        4,
    ]
