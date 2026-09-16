import logging

from rag.observability import Tracer
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

    def __init__(
        self,
        primary: BaseReranker,
        fallback: BaseReranker,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.tracer = tracer if tracer is not None else Tracer()

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            logger.warning("No candidates provided to reranker.")
            return []

        # Annotating the enclosing reranking span rather than opening one:
        # QueryService already times this call, and a second span would
        # duplicate that timing without adding anything. Until this was
        # recorded, a silent degradation to the fallback - or to no
        # reranking at all - showed up only as a log line nobody reads.
        try:
            results = self.primary.rerank(query, candidates, top_k)

            self.tracer.annotate(
                reranker_used=type(self.primary).__name__,
                reranker_degraded=False,
            )

            return results
        except Exception:
            logger.exception("Primary reranker failed; trying the fallback reranker.")

            self.tracer.annotate(primary_reranker_failed=True)

        try:
            results = self.fallback.rerank(query, candidates, top_k)

            self.tracer.annotate(
                reranker_used=type(self.fallback).__name__,
                reranker_degraded=True,
            )

            return results
        except Exception:
            logger.exception("Fallback reranker failed; returning retrieval order.")

            self.tracer.annotate(
                reranker_used="none",
                reranker_degraded=True,
            )

            return candidates[:top_k]
