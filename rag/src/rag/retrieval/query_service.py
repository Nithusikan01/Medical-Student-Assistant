import logging

from rag.observability import (
    Stage,
    Tracer,
    promotion_profile,
    rank_change,
    summarize_scores,
)
from rag.rerankers.base import BaseReranker
from rag.retrieval.base import BaseRetriever
from rag.retrieval.schemas import RetrievedChunk

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
        reranker: BaseReranker | None = None,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker
        self.tracer = tracer if tracer is not None else Tracer()

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

        with self.tracer.span(
            Stage.RETRIEVAL,
            top_k=top_k,
            candidate_k=candidate_k,
            use_reranker=use_reranker and self.reranker is not None,
        ) as span:

            #
            # Candidate retrieval
            #
            candidates = self.retriever.retrieve(
                query=query,
                top_k=candidate_k,
            )

            if not candidates:
                logger.warning("No retrieval results found.")

                span.set(candidate_count=0, final_count=0)

                return []

            logger.debug(
                "Retrieved %d candidate chunks.",
                len(candidates),
            )

            #
            # Optional reranking
            #
            if use_reranker and self.reranker is not None:

                logger.debug("Applying cross-encoder reranker.")

                # The span is opened here rather than inside the reranker,
                # so it covers whichever implementation is wired up.
                # FallbackReranker annotates it with which one actually
                # answered.
                with self.tracer.span(
                    Stage.RERANKING,
                    reranker=type(self.reranker).__name__,
                    candidate_count=len(candidates),
                    top_k=top_k,
                ) as rerank_span:

                    results = self.reranker.rerank(
                        query=query,
                        candidates=candidates,
                        top_k=top_k,
                    )

                    candidate_ids = [chunk.id for chunk in candidates]
                    selected_ids = [chunk.id for chunk in results]

                    rerank_span.set(
                        final_count=len(results),
                        # What changed, against the selection retrieval
                        # would have made on its own.
                        **rank_change(candidate_ids[:top_k], selected_ids),
                        # How deep into the candidate pool it reached,
                        # which is what says whether candidate_k is
                        # earning the latency it costs.
                        **promotion_profile(candidate_ids, selected_ids),
                        **summarize_scores(
                            chunk.rerank_score
                            for chunk in results
                            if chunk.rerank_score is not None
                        ),
                    )

            else:

                logger.debug("Skipping reranker.")

                results = candidates[:top_k]

            logger.info(
                "Returning %d retrieved chunks.",
                len(results),
            )

            span.set(
                candidate_count=len(candidates),
                final_count=len(results),
            )

            return results
