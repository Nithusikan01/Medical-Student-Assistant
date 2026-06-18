import logging
from pathlib import Path

from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.vectorstore.pinecone_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        document_loader: DocumentLoader,
        chunker: TextChunker,
        embedder: Embedder,
        vector_data_processor: VectorDataProcessor,
        vector_store: VectorStore
    ):
        self.document_loader = document_loader
        self.chunker = chunker
        self.embedder = embedder
        self.vector_data_processor = vector_data_processor
        self.vector_store = vector_store

    def run(self, file_path: str):
        try:
            logger.info("Starting ingestion pipeline for %s", file_path)

            # 1. Load document pages
            pages = self.document_loader.load(file_path)
            if not pages:
                raise ValueError("No pages loaded from document")

            # 2. Chunk pages
            chunks = self.chunker.chunk(pages)
            if not chunks:
                raise ValueError("No chunks generated")

            # 3. Embed chunks
            vectors = self.embedder.embed(chunks)
            if not vectors:
                raise ValueError("No embeddings generated")

            # 4. Build vector payload
            vector_data = self.vector_data_processor.prepare(
                vectors=vectors,
                chunks=chunks,
                source=Path(file_path).name
            )

            # 5. Store in vector DB
            self.vector_store.store_vectors(vector_data)

            logger.info("Completed ingestion pipeline for %s", file_path)

        except Exception as e:
            logger.exception("Pipeline failed for %s", file_path)
            raise