import logging
from collections import defaultdict

from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid retriever combining:

        - Dense vector retrieval
        - BM25 lexical retrieval

    Results are fused using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        dense_retriever: BaseRetriever,
        bm25_retriever: BaseRetriever,
        rrf_k: int = 60,
    ) -> None:
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve chunks using hybrid retrieval with Reciprocal Rank Fusion.
        """

        logger.debug(
            "Running hybrid retrieval for query: %s",
            query,
        )

        dense_results = self.dense_retriever.retrieve(
            query=query,
            top_k=top_k,
        )

        bm25_results = self.bm25_retriever.retrieve(
            query=query,
            top_k=top_k,
        )

        if not dense_results and not bm25_results:
            logger.warning("No results found from either retriever.")
            return []

        fused_scores: dict[str, float] = defaultdict(float)
        chunk_map: dict[str, RetrievedChunk] = {}

        def add_results(
            results: list[RetrievedChunk],
        ) -> None:

            for rank, chunk in enumerate(results, start=1):

                fused_scores[chunk.id] += 1.0 / (self.rrf_k + rank)

                #
                # Preserve scores from both retrievers.
                #
                if chunk.id not in chunk_map:
                    chunk_map[chunk.id] = chunk
                else:
                    existing = chunk_map[chunk.id]

                    chunk_map[chunk.id] = RetrievedChunk(
                        id=existing.id,
                        text=existing.text,
                        metadata=existing.metadata,
                        score=existing.score,
                        dense_score=(
                            existing.dense_score
                            if existing.dense_score is not None
                            else chunk.dense_score
                        ),
                        bm25_score=(
                            existing.bm25_score
                            if existing.bm25_score is not None
                            else chunk.bm25_score
                        ),
                        hybrid_score=existing.hybrid_score,
                        rerank_score=existing.rerank_score,
                        rank=existing.rank,
                        retrieval_method=existing.retrieval_method,
                    )

        add_results(dense_results)
        add_results(bm25_results)

        ranked_chunks = sorted(
            chunk_map.values(),
            key=lambda chunk: fused_scores[chunk.id],
            reverse=True,
        )

        final_results: list[RetrievedChunk] = []

        for rank, chunk in enumerate(ranked_chunks, start=1):

            final_results.append(
                chunk.with_hybrid_score(
                    score=fused_scores[chunk.id],
                    rank=rank,
                )
            )

        if top_k is not None:
            final_results = final_results[:top_k]

        logger.debug(
            "Hybrid retriever returned %d chunks.",
            len(final_results),
        )

        return final_results
