import logging

from sentence_transformers import SentenceTransformer

from rag_application.config.component_configs import RetrievalConfig
from rag_application.retrieval.base import BaseRetriever
from rag_application.retrieval.schemas import RetrievedChunk
from rag_application.vectorstore.base import VectorStoreInterface

logger = logging.getLogger(__name__)


class DenseRetriever(BaseRetriever):
    """
    Dense vector retriever using embedding similarity search.
    """

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding_model: SentenceTransformer
    ):
        self.vector_store = vector_store
        self.embedding_model = embedding_model

    def retrieve(
        self,
        query: str,
        top_k: int | None = None
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
            query
        )

        query_embedding = (
            self.embedding_model
            .encode(
                query,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            .tolist()
        )

        matches = self.vector_store.retrieve_vectors(
            query_vector=query_embedding,
            top_k=top_k
        )

        if not matches:
            logger.warning(
                "No dense retrieval matches found for query: %s",
                query
            )
            return []

        retrieved_chunks = []

        for match in matches:

            metadata = match.get("metadata", {})

            text = (
                metadata.get("original_text")
                or metadata.get("text")
                or metadata.get("content")
                or metadata.get("page_content")
            )

            if text is None:
                logger.warning(
                    "Skipping vector %s because text metadata is missing.",
                    match.get("id")
                )
                continue

            retrieved_chunks.append(
                RetrievedChunk(
                    id=match["id"],
                    score=float(match["score"]),
                    text=text,
                    metadata=metadata,
                    retrieval_method="dense"
                )
            )

        logger.debug(
            "Dense retriever returned %d chunks.",
            len(retrieved_chunks)
        )

        return retrieved_chunks