import logging
from pathlib import Path

from rag.ingestion.bm25 import BM25CorpusBuilder
from rag.ingestion.chunker import TextChunker
from rag.ingestion.document_loader import DocumentLoader
from rag.ingestion.embedder import Embedder
from rag.ingestion.processor import VectorDataProcessor
from rag.ingestion.sinks import ChunkSink
from rag.vectorstore.base import VectorStoreInterface

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Coordinates the complete document ingestion workflow.

        File
          │
          ▼
    DocumentLoader
          │
          ▼
    LoadedDocument
          │
          ▼
    TextChunker
          │
          ▼
    DocumentChunk
          │
          ▼
    Embedder
          │
          ▼
    EmbeddedChunk
          │
          ▼
    VectorDataProcessor
          │
          ▼
    VectorRecord
          │
          ▼
    VectorStore
    """

    def __init__(
        self,
        loader: DocumentLoader,
        chunker: TextChunker,
        embedder: Embedder,
        processor: VectorDataProcessor,
        vector_store: VectorStoreInterface,
        batch_size: int,
        bm25_corpus_path: str | Path | None = None,
        chunk_sink: ChunkSink | None = None,
    ) -> None:
        self.loader = loader
        self.chunker = chunker
        self.embedder = embedder
        self.processor = processor
        self.vector_store = vector_store
        self.batch_size = batch_size
        self.bm25_corpus_path = (
            Path(bm25_corpus_path) if bm25_corpus_path is not None else None
        )
        # Takes precedence over bm25_corpus_path when supplied.
        self.chunk_sink = chunk_sink

    def ingest(
        self,
        file_path: str | Path,
        document_id: str | None = None,
        chunk_sink: ChunkSink | None = None,
        filename: str | None = None,
    ) -> dict[str, int | str]:
        """
        Ingest a document into the vector store and BM25 corpus.
        """

        file_path = Path(file_path)
        source_name = filename or file_path.name

        logger.info(
            "Starting ingestion of '%s'.",
            source_name,
        )

        try:
            # ---------------------------------------------------------
            # Load document
            # ---------------------------------------------------------
            document = self.loader.load(
                str(file_path),
                document_id=document_id,
                filename=filename,
            )

            logger.info(
                "Loaded '%s' (%d pages).",
                document.filename,
                len(document.pages),
            )

            total_chunks = 0
            total_vectors = 0

            # A per-call sink wins, since it may be scoped to this document.
            bm25_builder = chunk_sink or self.chunk_sink

            if bm25_builder is None and self.bm25_corpus_path is not None:
                bm25_builder = BM25CorpusBuilder(self.bm25_corpus_path)

            with (
                bm25_builder if bm25_builder is not None else _NullContext()
            ) as builder:
                # ---------------------------------------------------------
                # Process document in batches
                # ---------------------------------------------------------
                for batch_number, chunk_batch in enumerate(
                    self.chunker.chunk_batches(
                        document=document,
                        batch_size=self.batch_size,
                    ),
                    start=1,
                ):

                    logger.info(
                        "Processing batch %d (%d chunks).",
                        batch_number,
                        len(chunk_batch),
                    )

                    if builder is not None:
                        builder.add_batch(chunk_batch)

                    # Generate embeddings
                    embedded_chunks = self.embedder.embed_batch(chunk_batch)

                    # Convert to vector records
                    vector_records = self.processor.prepare(embedded_chunks)

                    # Store vectors
                    self.vector_store.upsert(vector_records)

                    total_chunks += len(chunk_batch)
                    total_vectors += len(vector_records)

                    logger.info(
                        "Finished batch %d.",
                        batch_number,
                    )

            logger.info(
                ("Successfully ingested '%s'. " "(chunks=%d, vectors=%d)"),
                document.filename,
                total_chunks,
                total_vectors,
            )

            return {
                "document_id": document.document_id,
                "filename": document.filename,
                "pages": len(document.pages),
                "chunks": total_chunks,
                "vectors": total_vectors,
            }

        except Exception:
            logger.exception(
                "Failed to ingest document '%s'.",
                source_name,
            )
            raise


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False
