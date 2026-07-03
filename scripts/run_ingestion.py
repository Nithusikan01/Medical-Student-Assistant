from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


DEFAULT_PDF_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "cv.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a local PDF into Pinecone and refresh the BM25 corpus file."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=str(DEFAULT_PDF_PATH),
        help="Path to a local PDF file. Defaults to data/raw/cv.pdf.",
    )
    return parser.parse_args()


def build_ingestion_pipeline() -> IngestionPipeline:
    from rag_application.config.settings import load_settings
    from rag_application.ingestion.chunker import TextChunker
    from rag_application.ingestion.document_loader import DocumentLoader
    from rag_application.ingestion.embedder import Embedder
    from rag_application.ingestion.pipeline import IngestionPipeline
    from rag_application.ingestion.processor import VectorDataProcessor
    from rag_application.vectorstore.pinecone_store import PineconeVectorStore

    settings = load_settings()

    embedder = Embedder(settings.embedding_config())
    dimension = len(embedder.model.encode("dimension_check"))

    return IngestionPipeline(
        document_loader=DocumentLoader(),
        chunker=TextChunker(settings.chunking_config()),
        embedder=embedder,
        vector_data_processor=VectorDataProcessor(),
        vector_store=PineconeVectorStore(
            settings=settings,
            dimension=dimension,
        ),
    )


def main() -> int:
    args = parse_args()
    load_dotenv()

    from rag_application.utils.logger import setup_logging

    setup_logging()

    logger = logging.getLogger(__name__)
    file_path = Path(args.file_path).expanduser().resolve()

    if not file_path.exists():
        print(f"File not found: {file_path}")
        return 1

    if file_path.suffix.lower() != ".pdf":
        print(f"Only PDF ingestion is supported: {file_path}")
        return 1

    pipeline = build_ingestion_pipeline()
    pipeline.run(file_path)

    logger.info("Pipeline execution finished")
    print(f"Ingested PDF: {file_path}")
    print("Updated Pinecone vectors and storage/bm25_corpus.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
