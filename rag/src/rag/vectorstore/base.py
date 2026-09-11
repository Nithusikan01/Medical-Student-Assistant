from abc import ABC, abstractmethod
from collections.abc import Iterator

from rag.vectorstore.schemas import (
    SearchResult,
    VectorRecord,
)


class VectorStoreInterface(ABC):
    """
    Abstract interface for vector database implementations.

    Concrete implementations (e.g. Pinecone, Chroma, Qdrant)
    are responsible for translating these domain models into
    the format expected by the underlying vector database.
    """

    @abstractmethod
    def upsert(
        self,
        records: list[VectorRecord],
    ) -> int:
        """
        Insert new vectors or update existing ones.

        Args:
            records:
                Vector records to store.

        Returns:
            Number of vectors successfully upserted.
        """
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        Perform a similarity search.

        Args:
            embedding:
                Query embedding.

            top_k:
                Maximum number of similar vectors to return.

            filters:
                Optional metadata filters supported by the
                underlying vector database.

        Returns:
            Search results ordered by similarity score.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        ids: list[str],
    ) -> int:
        """
        Delete vectors by their IDs.

        Args:
            ids:
                IDs of vectors to remove.

        Returns:
            Number of vectors deleted.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_all(self) -> None:
        """
        Delete every vector stored in the index.
        """
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        """
        Return the total number of stored vectors.
        """
        raise NotImplementedError

    def list_ids(self, prefix: str) -> Iterator[str]:
        """
        Yield stored vector ids beginning with `prefix`.

        Deliberately not abstract: adding a required method would break
        existing implementations. Backends that cannot enumerate ids simply
        do not override it.
        """
        raise NotImplementedError("This vector store cannot list vector ids.")
