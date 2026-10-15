import logging

from rag.indexes.bm25_index import BM25Index
from rag.observability import Stage, Tracer, summarize_scores
from rag.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    Keyword-based retriever using a BM25 lexical index.
    """

    def __init__(
        self,
        bm25_index: BM25Index,
        *,
        default_top_k: int = 30,
        tracer: Tracer | None = None,
    ) -> None:
        self.bm25_index = bm25_index
        self.default_top_k = default_top_k
        self.tracer = tracer if tracer is not None else Tracer()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks using BM25 lexical search.
        """

        top_k = self.default_top_k if top_k is None else top_k

        with self.tracer.span(
            Stage.BM25_RETRIEVAL,
            top_k=top_k,
            # How much lexical corpus the index is actually searching. A
            # sudden drop here explains a retrieval regression that would
            # otherwise look like a scoring problem.
            corpus_size=getattr(self.bm25_index, "size", None),
        ) as span:

            results = self.bm25_index.search(
                query=query,
                top_k=top_k,
            )

            if not results:
                logger.warning("BM25 retrieval found no matches.")

                span.set(result_count=0)

                return []

            retrieved_chunks: list[RetrievedChunk] = []

            for rank, (chunk, score) in enumerate(results, start=1):

                metadata = RetrievedChunkMetadata(
                    document_id=chunk.metadata.document_id,
                    filename=chunk.metadata.filename,
                    source_path=chunk.metadata.source_path,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.metadata.page_number,
                    end_page_number=chunk.metadata.end_page_number,
                )

                retrieved_chunk = RetrievedChunk(
                    id=chunk.id,
                    text=chunk.text,
                    metadata=metadata,
                    score=0.0,
                ).with_bm25_score(
                    score=float(score),
                    rank=rank,
                )

                retrieved_chunks.append(retrieved_chunk)

            logger.debug(
                "BM25 retriever returned %d chunks.",
                len(retrieved_chunks),
            )

            span.set(
                result_count=len(retrieved_chunks),
                **summarize_scores(chunk.score for chunk in retrieved_chunks),
            )

            return retrieved_chunks
