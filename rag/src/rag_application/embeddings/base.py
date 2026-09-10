from typing import Protocol, runtime_checkable

from rag_application.ingestion.schemas import DocumentChunk, EmbeddedChunk


@runtime_checkable
class TextEmbedder(Protocol):
    """
    Turns text into vectors for both ingestion and querying.

    Defined so the retrieval and ingestion paths do not depend on any one
    embedding library: a local sentence-transformers model and a hosted API
    both satisfy it.
    """

    @property
    def dimension(self) -> int: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_batch(self, chunks: list[DocumentChunk]) -> list[EmbeddedChunk]: ...
