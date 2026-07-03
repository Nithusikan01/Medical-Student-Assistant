import logging
from collections import defaultdict

from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining:
        - Dense vector search
        - BM25 lexical search

    Uses Reciprocal Rank Fusion (RRF) to merge rankings.
    """

    def __init__(
        self,
        dense_retriever: BaseRetriever,
        bm25_retriever: BaseRetriever,
        rrf_k: int = 60
    ):
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        top_k: int | None = None
    ) -> list[RetrievedChunk]:

        logger.debug("Running hybrid retrieval for query: %s", query)

        # 1. Get results from both retrievers
        dense_results = self.dense_retriever.retrieve(query)
        bm25_results = self.bm25_retriever.retrieve(query)

        if not dense_results and not bm25_results:
            logger.warning("No results found from either retriever.")
            return []

        # 2. Score aggregation using RRF
        fused_scores = defaultdict(float)
        chunk_map = {}

        def add_results(results: list[RetrievedChunk]):
            for rank, chunk in enumerate(results, start=1):

                # RRF score
                fused_scores[chunk.id] += 1.0 / (self.rrf_k + rank)

                # keep latest reference (metadata/text)
                chunk_map[chunk.id] = chunk

        add_results(dense_results)
        add_results(bm25_results)

        # 3. Sort by fused score
        ranked_chunks = sorted(
            chunk_map.values(),
            key=lambda c: fused_scores[c.id],
            reverse=True
        )

        # 4. Attach final hybrid score
        final_results = []
        for chunk in ranked_chunks:

            final_results.append(
                RetrievedChunk(
                    id=chunk.id,
                    score=fused_scores[chunk.id],
                    text=chunk.text,
                    metadata=chunk.metadata,
                    retrieval_method="hybrid"
                )
            )

        # 5. Apply final top_k cutoff
        if top_k is not None:
            final_results = final_results[:top_k]

        logger.debug(
            "Hybrid retrieval returned %d chunks",
            len(final_results)
        )

        return final_results