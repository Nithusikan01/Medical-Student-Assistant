import logging
from typing import Any

from rag_application.config.component_configs import RetrievalConfig
from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)
from rag_application.vectorstore.base import VectorStoreInterface

logger = logging.getLogger(__name__)


class DenseRetriever(BaseRetriever):
    """
    Dense vector retriever using embedding similarity search.
    """

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding_model: Any,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks using dense vector search.
        """

        top_k = (
            RetrievalConfig().candidate_k
            if top_k is None
            else top_k
        )

        logger.debug(
            "Running dense retrieval for query: %s",
            query,
        )

        query_embedding = (
            self.embedding_model.encode(
                query,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).tolist()
        )

        matches = self.vector_store.query(
            embedding=query_embedding,
            top_k=top_k,
            filters=None,
        )

        if not matches:
            logger.warning(
                "No dense retrieval matches found for query: %s",
                query,
            )
            return []

        retrieved_chunks: list[RetrievedChunk] = []

        for rank, match in enumerate(matches, start=1):
            metadata = match.metadata

            if metadata.text is None:
                logger.warning(
                    "Skipping vector '%s' because text metadata is missing.",
                    match.id,
                )
                continue

            chunk_metadata = RetrievedChunkMetadata(
                document_id=metadata.document_id,
                filename=metadata.filename,
                source_path=metadata.source_path,
                chunk_index=metadata.chunk_index,
                page_number=metadata.page_number,
                section_title=metadata.section_title,
                heading_level=metadata.heading_level,
            )

            chunk = RetrievedChunk(
                id=match.id,
                text=metadata.text,
                metadata=chunk_metadata,
                score=0.0,
            ).with_dense_score(
                score=float(match.score),
                rank=rank,
            )

            retrieved_chunks.append(chunk)

        logger.debug(
            "Dense retriever returned %d chunks.",
            len(retrieved_chunks),
        )

        return retrieved_chunks
