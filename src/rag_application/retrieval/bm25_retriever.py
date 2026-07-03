import logging

from rag_application.indexes.bm25_index import BM25Index
from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import RetrievedChunk
from rag_application.config.component_configs import RetrievalConfig

logger = logging.getLogger(__name__)


class BM25Retriever(BaseRetriever):
    """
    Keyword-based retriever using a BM25 lexical index.
    """

    def __init__(
        self,
        bm25_index: BM25Index
    ):
        self.bm25_index = bm25_index

    def retrieve(
        self,
        query: str,
        top_k: int | None = None
    ) -> list[RetrievedChunk]:

        top_k = (
            RetrievalConfig().candidate_k
            if top_k is None
            else top_k
        )

        results = self.bm25_index.search(
            query=query,
            top_k=top_k
        )

        if not results:
            logger.warning(
                "No BM25 matches found for query: %s",
                query
            )
            return []

        retrieved_chunks = []

        for chunk, score in results:

            metadata = {
                "source": chunk.source,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "timestamp": chunk.timestamp,
                "original_text": chunk.text,
            }

            retrieved_chunks.append(
                RetrievedChunk(
                    id=chunk.id,
                    score=score,
                    text=chunk.text,
                    metadata=metadata,
                    retrieval_method="bm25"
                )
            )

        logger.debug(
            "BM25 retrieved %d chunks.",
            len(retrieved_chunks)
        )

        return retrieved_chunks