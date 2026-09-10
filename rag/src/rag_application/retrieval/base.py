from abc import ABC, abstractmethod

from rag_application.retrieval.schemas import RetrievedChunk


class BaseRetriever(ABC):
    """
    Base class for every retrieval strategy.
    All retrievers must return ranked chunks.
    """

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query: User query.
            top_k: Number of chunks to return. If None, the retriever
                should use its configured default.

        Returns:
            A list of RetrievedChunk objects ordered by decreasing relevance.
        """
        raise NotImplementedError