from typing import Protocol, Self, runtime_checkable

from rag_application.ingestion.schemas import DocumentChunk


@runtime_checkable
class ChunkSink(Protocol):
    """
    Receives each batch of chunks as the pipeline produces them.

    BM25CorpusBuilder satisfies this for file-backed corpora, so the engine
    stays usable without a database. An application that stores chunks
    elsewhere supplies its own implementation instead.
    """

    def add_batch(self, chunks: list[DocumentChunk]) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc_value, traceback) -> bool: ...
