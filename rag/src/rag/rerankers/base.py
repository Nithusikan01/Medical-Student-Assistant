from typing import Protocol, runtime_checkable

from rag.retrieval.schemas import RetrievedChunk


@runtime_checkable
class BaseReranker(Protocol):
    """
    Anything that reorders retrieved candidates for a query.

    Implementations are expected to raise on failure rather than degrade
    themselves; FallbackReranker decides what happens next.
    """

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
        ...
