import logging

from rag.rerankers.base import BaseReranker
from rag.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class FallbackReranker(BaseReranker):
    """
    Tries a primary reranker, falls back to a secondary one, and finally
    falls back to the untouched retrieval order.

    This is the one place that decides "give up and skip reranking" - the
    rerankers it wraps are expected to raise on failure rather than degrade
    themselves, so failures from either stage are handled the same way here.
    """

    def __init__(self, primary: BaseReranker, fallback: BaseReranker) -> None:
        self.primary = primary
        self.fallback = fallback

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            logger.warning("No candidates provided to reranker.")
            return []

        try:
            return self.primary.rerank(query, candidates, top_k)
        except Exception:
            logger.exception("Primary reranker failed; trying the fallback reranker.")

        try:
            return self.fallback.rerank(query, candidates, top_k)
        except Exception:
            logger.exception("Fallback reranker failed; returning retrieval order.")
            return candidates[:top_k]
