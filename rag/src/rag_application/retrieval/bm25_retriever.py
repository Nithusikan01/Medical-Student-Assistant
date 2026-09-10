import logging

from rag_application.config.component_configs import RetrievalConfig
from rag_application.indexes.bm25_index import BM25Index
from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)

logger = logging.getLogger(__name__)


class BM25Retriever(BaseRetriever):
    """
    Keyword-based retriever using a BM25 lexical index.
    """

    def __init__(
        self,
        bm25_index: BM25Index,
    ) -> None:
        self.bm25_index = bm25_index

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks using BM25 lexical search.
        """

        top_k = RetrievalConfig().candidate_k if top_k is None else top_k

        logger.debug(
            "Running BM25 retrieval for query: %s",
            query,
        )

        results = self.bm25_index.search(
            query=query,
            top_k=top_k,
        )

        if not results:
            logger.warning(
                "No BM25 matches found for query: %s",
                query,
            )
            return []

        retrieved_chunks: list[RetrievedChunk] = []

        for rank, (chunk, score) in enumerate(results, start=1):

            metadata = RetrievedChunkMetadata(
                document_id=chunk.metadata.document_id,
                filename=chunk.metadata.filename,
                source_path=chunk.metadata.source_path,
                chunk_index=chunk.chunk_index,
                page_number=chunk.metadata.page_number,
                section_title=chunk.metadata.section_title,
                heading_level=chunk.metadata.heading_level,
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

        return retrieved_chunks
