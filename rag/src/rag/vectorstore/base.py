from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from rag.vectorstore.schemas import (
    SearchResult,
    VectorRecord,
)


@runtime_checkable
class VectorStoreInterface(Protocol):
    """
    What the engine needs from a vector database.

    A Protocol rather than an abstract base class, so an implementation
    (Pinecone here; Chroma or Qdrant elsewhere) satisfies it by shape and
    test doubles need no inheritance. Optional capabilities are separate
    protocols - see IdListingVectorStore - rather than methods that raise
    NotImplementedError, so whether a store supports one is a type
    question, not a runtime surprise.
    """

    def upsert(
        self,
        records: list[VectorRecord],
    ) -> int:
        """
        Insert new vectors or update existing ones.

        Returns:
            Number of vectors successfully upserted.
        """
        ...

    def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        Perform a similarity search.

        Args:
            embedding: Query embedding.
            top_k: Maximum number of similar vectors to return.
            filters: Optional metadata filters supported by the underlying
                vector database.

        Returns:
            Search results ordered by similarity score.
        """
        ...

    def delete(
        self,
        ids: list[str],
    ) -> int:
        """
        Delete vectors by their IDs.

        Returns:
            Number of vectors deleted.
        """
        ...

    def count(self) -> int:
        """
        Return the total number of stored vectors.
        """
        ...


@runtime_checkable
class IdListingVectorStore(VectorStoreInterface, Protocol):
    """
    A vector store that can enumerate its ids by prefix.

    Used only for admin-triggered reconciliation (purging vectors no chunk
    row points at). Stores that cannot list ids simply do not satisfy it.
    """

    def list_ids(self, prefix: str) -> Iterator[str]:
        """
        Yield stored vector ids beginning with `prefix`.
        """
        ...
