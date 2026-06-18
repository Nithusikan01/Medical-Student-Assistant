from typing import List
import logging

from sentence_transformers import SentenceTransformer

from rag_application.utils.exceptions import EmbeddingError
from rag_application.config.component_configs import EmbeddingConfig


logger = logging.getLogger(__name__)

class Embedder:
    def __init__(
            self, 
            config: EmbeddingConfig
    ):
        self.model = SentenceTransformer(config.model_name)

    def embed(self, chunks: List[str]) -> List[List[float]]:
        try:
            embeddings = self.model.encode(chunks).tolist()

            if not embeddings:
                raise EmbeddingError("Failed to generate embeddings.")
            
            logger.info(
                "Embeded %d chunks (dim=%d)",
                len(chunks),
                len(embeddings[0]) 
            )

            return embeddings
        
        except Exception as e:
            logger.exception("Error during embedding: %s", str(e))
            raise EmbeddingError(f"Embedding failed: {str(e)}") from e
