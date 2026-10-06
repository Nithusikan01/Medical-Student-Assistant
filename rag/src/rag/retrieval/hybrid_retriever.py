import logging
from collections import defaultdict

from rag.observability import Stage, Tracer
from rag.retrieval.base import BaseRetriever
from rag.retrieval.schemas import RetrievedChunk

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
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k
        self.tracer = tracer if tracer is not None else Tracer()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
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
            query_embedding=query_embedding,
        )

        bm25_results = self.bm25_retriever.retrieve(
            query=query,
            top_k=top_k,
        )

        dense_results, dense_dropped = self._only_listed_documents(dense_results)

        if not dense_results and not bm25_results:
            logger.warning("No results found from either retriever.")

            # Recorded even though there is nothing to fuse: "both
            # retrievers came back empty" is exactly the case worth being
            # able to count later.
            with self.tracer.span(
                Stage.FUSION,
                method="rrf",
                rrf_k=self.rrf_k,
                dense_count=0,
                bm25_count=0,
                dense_unlisted_count=dense_dropped,
                fused_count=0,
            ):
                return []

        dense_ids = {chunk.id for chunk in dense_results}
        bm25_ids = {chunk.id for chunk in bm25_results}

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

        with self.tracer.span(
            Stage.FUSION,
            method="rrf",
            rrf_k=self.rrf_k,
            dense_count=len(dense_results),
            bm25_count=len(bm25_results),
            # How much the two retrievers agreed. A collapsing overlap is
            # the signal that one of them has stopped contributing - which
            # no single retriever's own metrics would show.
            overlap_count=len(dense_ids & bm25_ids),
            unique_count=len(dense_ids | bm25_ids),
            dense_only_count=len(dense_ids - bm25_ids),
            bm25_only_count=len(bm25_ids - dense_ids),
            # Non-zero means Pinecone holds vectors for a document that is
            # not ready - a failed upload, or a delete that stalled.
            dense_unlisted_count=dense_dropped,
        ) as span:

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

            span.set(fused_count=len(final_results))

            return final_results

    def _only_listed_documents(
        self,
        dense_results: list[RetrievedChunk],
    ) -> tuple[list[RetrievedChunk], int]:
        """
        Drop dense hits from documents the lexical index does not hold.

        The two halves are not equally up to date. The BM25 index is built
        from documents whose status is `ready`, and is rebuilt the moment one
        is ingested or delisted. Pinecone holds whatever was upserted:
        vectors from an upload that failed halfway, from one still in
        progress, or from a delete whose vector call failed and left the
        document in `deleting`. Searched unfiltered, those reach answers
        while the document is listed nowhere - so the BM25 index's
        documents are treated as the set allowed to appear at all.

        Skipped when the lexical retriever cannot say which documents it
        holds, so a retriever without that property keeps the old behaviour.
        """

        listed = getattr(self.bm25_retriever, "document_ids", None)

        if not isinstance(listed, (set, frozenset)):
            return dense_results, 0

        kept = [
            chunk
            for chunk in dense_results
            if str(chunk.metadata.document_id) in listed
        ]

        dropped = len(dense_results) - len(kept)

        if dropped:
            logger.warning(
                "Dropped %d dense result(s) from documents that are not ready.",
                dropped,
            )

        return kept, dropped
