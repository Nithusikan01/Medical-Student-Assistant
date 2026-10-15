import logging
from contextlib import nullcontext
from pathlib import Path

from rag.embeddings.base import TextEmbedder
from rag.ingestion.chunker import TextChunker
from rag.ingestion.document_loader import DocumentLoader
from rag.ingestion.processor import VectorDataProcessor
from rag.ingestion.schemas import DocumentChunk, EmbeddedChunk
from rag.ingestion.sinks import ChunkSink
from rag.observability import Stage, Tracer
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
        embedder: TextEmbedder,
        processor: VectorDataProcessor,
        vector_store: VectorStoreInterface,
        batch_size: int,
        chunk_sink: ChunkSink | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.loader = loader
        self.chunker = chunker
        self.embedder = embedder
        self.processor = processor
        self.vector_store = vector_store
        self.batch_size = batch_size

        # Where each batch's chunks go besides the vector store - the BM25
        # text source. Optional: ingesting vectors only is a valid use. Pass
        # BM25CorpusBuilder(path) for a file-backed corpus with no database.
        self.chunk_sink = chunk_sink

        # Defaults to a tracer that records nothing, so the pipeline stays
        # runnable with no telemetry backend - the same contract the query
        # service follows.
        self.tracer = tracer if tracer is not None else Tracer()

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
            with self.tracer.span(Stage.INGESTION) as ingestion:
                # ---------------------------------------------------------
                # Load document
                # ---------------------------------------------------------
                with self.tracer.span(Stage.DOCUMENT_LOAD) as load:
                    document = self.loader.load(
                        str(file_path),
                        document_id=document_id,
                        filename=filename,
                    )

                    load.set(pages=len(document.pages))

                logger.info(
                    "Loaded '%s' (%d pages).",
                    document.filename,
                    len(document.pages),
                )

                total_chunks = 0
                total_vectors = 0

                # Initialised rather than left to the loop: a PDF with no
                # extractable text yields no batches at all, and the span
                # below still has to report how many there were.
                batch_number = 0

                # A per-call sink wins, since it may be scoped to this document.
                sink = chunk_sink or self.chunk_sink

                # Each batch goes to the sink before it is embedded and
                # upserted. The two stores are not written atomically: if a
                # later batch fails, vectors from earlier batches may remain
                # after the sink discards its rows (the backend's purge
                # sweeps those by id prefix).
                with sink if sink is not None else nullcontext() as builder:
                    # -----------------------------------------------------
                    # Process document in batches
                    # -----------------------------------------------------
                    #
                    # Chunking gets no span of its own. chunk_batches is a
                    # generator that splits page by page as batches are
                    # pulled; a span around the loop would re-time the whole
                    # ingestion under a name that claims to be chunking.
                    for batch_number, chunk_batch in enumerate(
                        self.chunker.chunk_batches(
                            document=document,
                            batch_size=self.batch_size,
                        ),
                        start=1,
                    ):
                        with self.tracer.span(
                            Stage.INGESTION_BATCH,
                            batch=batch_number,
                            chunks=len(chunk_batch),
                        ):
                            logger.info(
                                "Processing batch %d (%d chunks).",
                                batch_number,
                                len(chunk_batch),
                            )

                            if builder is not None:
                                builder.add_batch(chunk_batch)

                            # Generate embeddings
                            with self.tracer.span(
                                Stage.DOCUMENT_EMBEDDING,
                                chunks=len(chunk_batch),
                            ):
                                embedded_chunks = self._embed(chunk_batch)

                            # Convert to vector records
                            vector_records = self.processor.prepare(embedded_chunks)

                            # Store vectors
                            with self.tracer.span(
                                Stage.VECTOR_UPSERT,
                                vectors=len(vector_records),
                            ):
                                self.vector_store.upsert(vector_records)

                            total_chunks += len(chunk_batch)
                            total_vectors += len(vector_records)

                            logger.info(
                                "Finished batch %d.",
                                batch_number,
                            )

                ingestion.set(
                    pages=len(document.pages),
                    chunks=total_chunks,
                    vectors=total_vectors,
                    batches=batch_number,
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

    def _embed(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])

        if len(vectors) != len(chunks):
            raise ValueError(
                f"Embedder returned {len(vectors)} vectors for {len(chunks)} chunks."
            )

        return [
            EmbeddedChunk(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                metadata=chunk.metadata,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
