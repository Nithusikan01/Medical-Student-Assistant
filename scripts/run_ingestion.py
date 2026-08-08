from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from rag_application.config.settings import load_settings
from rag_application.ingestion.bm25 import BM25CorpusBuilder
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.document_loader import DocumentLoader

load_dotenv()

PDF = Path("data/raw/cv.pdf")
OUTPUT = Path("storage/test_bm25.json")


def main():

    settings = load_settings()

    loader = DocumentLoader()
    chunker = TextChunker(settings.chunking_config())

    pages = loader.load(PDF)

    chunks = chunker.chunk(
        pages=pages,
        source=PDF.name,
    )

    with BM25CorpusBuilder(OUTPUT) as builder:

        for batch in chunker.chunk_batches(
            pages=pages,
            source=PDF.name,
            batch_size=5,
            
        ):
            builder.add_batch(batch)

    corpus = json.loads(
        OUTPUT.read_text(
            encoding="utf-8"
        )
    )

    print()

    print("=" * 60)
    print("BM25 Builder Verification")
    print("=" * 60)

    print(f"Chunks      : {len(chunks)}")
    print(f"BM25 Records: {len(corpus)}")

    assert len(chunks) == len(corpus)

    for chunk, record in zip(chunks, corpus):

        assert chunk.id == record["id"]
        assert chunk.text == record["text"]

        assert (
            chunk.source
            == record["metadata"]["source"]
        )

        assert (
            chunk.chunk_index
            == record["metadata"]["chunk_index"]
        )

        assert (
            chunk.timestamp
            == record["metadata"]["timestamp"]
        )

    print()
    print("✅ BM25 corpus verified.")
    print()


if __name__ == "__main__":
    main()