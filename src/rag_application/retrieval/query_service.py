import logging

from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.reranker import Reranker
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class QueryService:
    """
    Orchestrates the full retrieval pipeline:

        Hybrid Retrieval → Reranking → Final Context

    This is the ONLY class the LLM layer should interact with.
    """

    def __init__(
        self,
        retriever: BaseRetriever,
        reranker: Reranker | None = None
    ):
        self.retriever = retriever
        self.reranker = reranker

    def search(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 20,
        use_reranker: bool = True
    ) -> list[RetrievedChunk]:

        logger.info("QueryService received query: %s", query)

        # -----------------------------
        # 1. Candidate Retrieval
        # -----------------------------
        candidates = self.retriever.retrieve(
            query=query,
            top_k=candidate_k
        )

        if not candidates:
            logger.warning("No candidates found for query: %s", query)
            return []

        logger.debug(
            "Retrieved %d candidate chunks",
            len(candidates)
        )

        # -----------------------------
        # 2. Reranking (optional)
        # -----------------------------
        if use_reranker and self.reranker:

            logger.debug("Applying reranker...")

            final_results = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k
            )

        else:
            # fallback: no reranking
            final_results = candidates[:top_k]

            logger.warning(
                "Reranker not used. Returning raw retrieval results."
            )

        # -----------------------------
        # 3. Return final context
        # -----------------------------
        logger.info(
            "QueryService returning %d final chunks",
            len(final_results)
        )

        return final_results