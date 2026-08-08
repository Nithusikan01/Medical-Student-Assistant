import logging

from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.reranker import Reranker
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class QueryService:
    """
    Orchestrates the retrieval pipeline.

        Retriever
            ↓
        Optional Reranker
            ↓
        Final Retrieved Chunks

    This is the entry point used by the RAG pipeline.
    """

    def __init__(
        self,
        retriever: BaseRetriever,
        reranker: Reranker | None = None,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker

    def search(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 20,
        use_reranker: bool = True,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query:
                User query.

            top_k:
                Number of chunks returned to the generator.

            candidate_k:
                Number of chunks retrieved before reranking.

            use_reranker:
                Whether to apply the cross-encoder reranker.

        Returns:
            Ranked list of RetrievedChunk objects.
        """

        logger.info(
            "Retrieving candidates for query: %s",
            query,
        )

        #
        # Candidate retrieval
        #
        candidates = self.retriever.retrieve(
            query=query,
            top_k=candidate_k,
        )

        if not candidates:
            logger.warning(
                "No retrieval results found."
            )
            return []

        logger.debug(
            "Retrieved %d candidate chunks.",
            len(candidates),
        )

        #
        # Optional reranking
        #
        if use_reranker and self.reranker is not None:

            logger.debug(
                "Applying cross-encoder reranker."
            )

            results = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k,
            )

        else:

            logger.debug(
                "Skipping reranker."
            )

            results = candidates[:top_k]

        logger.info(
            "Returning %d retrieved chunks.",
            len(results),
        )

        return results