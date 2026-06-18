import logging
from sentence_transformers import SentenceTransformer

from rag_application.vectorstore.base import VectorStoreInterface
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

        matches = self.vector_store.similarity_search(
            query_vector=query_embedding,
            top_k=top_k
        )

        if not matches:
            logger.warning(f"No matches found for query: {query}")
            return []

        return [
            RetrievedChunk(
                id=match["id"],
                score=match["score"],
                text=match["metadata"]["original_text"],
                metadata=match["metadata"]
            )
            for match in matches
        ]