from typing import Protocol, runtime_checkable


@runtime_checkable
class TextEmbedder(Protocol):
    """
    Turns text into vectors for both ingestion and querying.

    Defined so the retrieval and ingestion paths do not depend on any one
    embedding library: a local sentence-transformers model and a hosted API
    both satisfy it.

    Plain strings in, plain vectors out. Pairing a vector with the chunk it
    came from is the ingestion pipeline's business, so the query side - the
    retriever and the response cache - never has to import ingestion types.

    Queries and documents are separate methods because hosted models are
    trained asymmetrically: embedding a query as a passage measurably
    degrades retrieval.
    """

    @property
    def dimension(self) -> int: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
