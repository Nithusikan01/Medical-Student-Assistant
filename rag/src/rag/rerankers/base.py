from abc import ABC, abstractmethod

from rag.retrieval.schemas import RetrievedChunk


class BaseReranker(ABC):
    """
    Base class for every reranking strategy.
    All rerankers must return ranked chunks.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """
        Rerank candidate chunks for a query.

        Args:
            query: User query.
            candidates: Chunks to rerank, in their prior order.
            top_k: Number of chunks to return.

        Returns:
            A list of RetrievedChunk objects ordered by decreasing relevance.
        """
        raise NotImplementedError
