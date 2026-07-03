import logging
from typing import List

from sentence_transformers import CrossEncoder

from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder based reranker for improving retrieval quality.

    Takes a list of candidate chunks and reranks them using
    a query-aware deep relevance model.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base"
    ):
        logger.info("Loading reranker model: %s", model_name)

        self.model = CrossEncoder(model_name)

        logger.info("Reranker model loaded successfully.")

    def rerank(
        self,
        query: str,
        candidates: List[RetrievedChunk],
        top_k: int = 5
    ) -> List[RetrievedChunk]:

        if not candidates:
            logger.warning("No candidates provided to reranker.")
            return []

        logger.debug(
            "Reranking %d candidates for query: %s",
            len(candidates),
            query
        )

        # 1. Prepare (query, document) pairs
        pairs = [
            (query, chunk.text)
            for chunk in candidates
        ]

        # 2. Predict relevance scores
        scores = self.model.predict(pairs)

        # 3. Attach scores to chunks
        reranked = []
        for chunk, score in zip(candidates, scores):

            reranked.append(
                RetrievedChunk(
                    id=chunk.id,
                    score=float(score),
                    text=chunk.text,
                    metadata=chunk.metadata,
                    retrieval_method=f"rerank({chunk.retrieval_method})"
                )
            )

        # 4. Sort by reranker score
        reranked.sort(
            key=lambda x: x.score,
            reverse=True
        )

        # 5. Return top_k
        final_results = reranked[:top_k]

        logger.debug(
            "Reranker reduced %d → %d chunks",
            len(candidates),
            len(final_results)
        )

        return final_results