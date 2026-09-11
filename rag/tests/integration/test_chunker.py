from pathlib import Path

from rag.config.component_configs import ChunkingConfig
from rag.ingestion.chunker import TextChunker
from rag.ingestion.schemas import LoadedDocument, LoadedPage

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
OUTPUT_PATH = FIXTURES_DIR / "output.txt"


def test_chunker_with_valid_input():
    document = LoadedDocument(
        document_id="output",
        filename="output.txt",
        source_path=str(OUTPUT_PATH),
        pages=[
            LoadedPage(
                page_number=1,
                text=OUTPUT_PATH.read_text(encoding="utf-8"),
            )
        ],
    )
    chunker = TextChunker(
        config=ChunkingConfig(
            chunk_size=500,
            chunk_overlap=50,
        )
    )

    chunks = chunker.chunk(document)

    assert chunks
    assert chunks[0].metadata.filename == "output.txt"
    assert chunks[0].text
    assert chunks[0].id == "output_chunk_0"
