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


def _document(*pages: tuple[int, str]) -> LoadedDocument:
    return LoadedDocument(
        document_id="doc",
        filename="doc.pdf",
        source_path="/tmp/doc.pdf",
        pages=[LoadedPage(page_number=n, text=text) for n, text in pages],
    )


SPLIT_SENTENCE = _document(
    (1, "Sepsis is a life-threatening organ dysfunction caused by a dysregulated host"),
    (2, "response to infection. It is diagnosed with the SOFA score."),
)


def test_a_sentence_across_a_page_break_stays_in_one_chunk():
    """
    Splitting page by page cut this sentence into two fragments, neither
    of which a question about sepsis's definition could match.
    """

    chunks = TextChunker(ChunkingConfig(chunk_size=500, chunk_overlap=50)).chunk(
        SPLIT_SENTENCE
    )

    assert len(chunks) == 1
    assert "dysregulated host\nresponse to infection" in chunks[0].text
    assert chunks[0].metadata.page_number == 1
    assert chunks[0].metadata.end_page_number == 2


def test_offsets_slice_back_to_the_chunk_text_and_pages_follow_them():
    document = _document(
        (1, "Alpha paragraph one.\n\nAlpha paragraph two is here."),
        (3, "Gamma page text.\n\nGamma closing words."),
        (4, "Delta only."),
    )
    text = "\n".join(page.text for page in document.pages)

    chunks = TextChunker(ChunkingConfig(chunk_size=40, chunk_overlap=10)).chunk(
        document
    )

    assert len(chunks) > 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))

    for chunk in chunks:
        metadata = chunk.metadata
        assert text[metadata.start_char : metadata.end_char] == chunk.text
        assert metadata.page_number <= metadata.end_page_number

    # Page numbers are the PDF's, not positions in the list: page 2 had no
    # text and was dropped by the loader.
    assert chunks[0].metadata.page_number == 1
    assert chunks[-1].metadata.end_page_number == 4
    assert {chunk.metadata.page_number for chunk in chunks} <= {1, 3, 4}


def test_chunk_batches_cover_every_chunk_in_order():
    document = _document(*[(n, f"Page {n} has its own sentence.") for n in range(1, 8)])
    chunker = TextChunker(ChunkingConfig(chunk_size=30, chunk_overlap=0))

    batches = list(chunker.chunk_batches(document, batch_size=3))

    assert all(len(batch) <= 3 for batch in batches)
    assert [c.id for batch in batches for c in batch] == [
        c.id for c in chunker.chunk(document)
    ]
