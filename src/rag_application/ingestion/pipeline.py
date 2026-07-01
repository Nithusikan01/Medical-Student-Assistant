import logging
from os import PathLike
from pathlib import Path

from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.vectorstore.pinecone_store import PineconeVectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
            self, 
            document_loader: DocumentLoader,
            chunker: TextChunker,
            embedder: Embedder, 
            vector_data_processor: VectorDataProcessor,
            vector_store: PineconeVectorStore
    ):
        self.document_loader = document_loader
        self.chunker = chunker
        self.embedder = embedder
        self.vector_data_processor = vector_data_processor
        self.vector_store = vector_store

    def run(self, file_path: str | PathLike[str]):
        logger.info("Starting ingestion pipeline for %s", file_path)

        pages = self.document_loader.load(file_path)

        chunks = self.chunker.chunk(pages)

        vectors = self.embedder.embed(chunks)

        vector_data = self.vector_data_processor.prepare(
            vectors=vectors,
            chunks=chunks,
            source=Path(file_path).name
        )

        self.vector_store.store_vectors(vector_data)

        logger.info("Completed ingestion pipeline for %s", file_path)
