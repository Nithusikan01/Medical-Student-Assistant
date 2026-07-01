import logging
from sentence_transformers import SentenceTransformer

from rag_application.vectorstore.base import VectorStoreInterface
from rag_application.config.component_configs import RetrievalConfig
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

class Retriever:
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
            top_k: int = 5
    ) -> list[RetrievedChunk]:
        
        query_embedding = (
            self.embedding_model
            .encode(query)
            .tolist()
        )
        
        top_k = RetrievalConfig().final_context_k if top_k is None else top_k
        matches = self.vector_store.similarity_search(
            query_vector=query_embedding,
            top_k=top_k
        )

        if not matches:
            logger.warning(f"No matches found for query: {query}")
            return []

        retrieved_chunks = []

        for match in matches:
            metadata = match.get("metadata") or {}
            text = (
                metadata.get("original_text")
                or metadata.get("text")
                or metadata.get("content")
                or metadata.get("page_content")
            )

            if not text:
                logger.warning(
                    "Skipping retrieved match %s because metadata has no text field. Metadata keys: %s",
                    match.get("id"),
                    sorted(metadata.keys()),
                )
                continue

            retrieved_chunks.append(
                RetrievedChunk(
                    id=match["id"],
                    score=match["score"],
                    text=text,
                    metadata=metadata
                )
            )

        return retrieved_chunks
