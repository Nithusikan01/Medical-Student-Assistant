import logging

from sentence_transformers import CrossEncoder

from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder based reranker.

    Takes candidate chunks from a retriever and reranks them using
    a query-document relevance model.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
    ) -> None:
        logger.info(
            "Loading reranker model: %s",
            model_name,
        )

        self.model = CrossEncoder(model_name)

        logger.info(
            "Reranker model loaded successfully."
        )

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:

        if not candidates:
            logger.warning(
                "No candidates provided to reranker."
            )
            return []

        logger.debug(
            "Reranking %d candidates.",
            len(candidates),
        )

        #
        # Prepare (query, document) pairs.
        #
        pairs = [
            (query, chunk.text)
            for chunk in candidates
        ]

        #
        # CrossEncoder scores.
        #
        scores = self.model.predict(pairs)

        #
        # Update each chunk with its rerank score.
        #
        reranked = [
            chunk.with_rerank_score(
                score=float(score)
            )
            for chunk, score in zip(
                candidates,
                scores,
            )
        ]

        #
        # Sort by reranker score.
        #
        reranked.sort(
            key=lambda chunk: chunk.score,
            reverse=True,
        )

        #
        # Update final ranks.
        #
        reranked = [
            chunk.with_rerank_score(
                score=chunk.score,
                rank=rank,
            )
            for rank, chunk in enumerate(
                reranked,
                start=1,
            )
        ]

        final_results = reranked[:top_k]

        logger.debug(
            "Reranker reduced %d candidates to %d.",
            len(candidates),
            len(final_results),
        )

        return final_results