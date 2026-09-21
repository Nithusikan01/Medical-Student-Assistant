from abc import ABC, abstractmethod

from rag.retrieval.schemas import RetrievedChunk


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
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query: User query.
            top_k: Number of chunks to return. If None, the retriever
                should use its configured default.
            query_embedding: A vector for `query` the caller has already
                computed. Optional and only meaningful to retrievers that
                embed: a lexical retriever ignores it. Passing it avoids
                embedding the same text twice when something upstream -
                the response cache - has already paid for it.

        Returns:
            A list of RetrievedChunk objects ordered by decreasing relevance.
        """
        raise NotImplementedError
