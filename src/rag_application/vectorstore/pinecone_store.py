import logging
import time
from typing import List, Dict
from pinecone import Pinecone, ServerlessSpec

from rag_application.config.settings import Settings
from rag_application.vectorstore.base import VectorStoreInterface
from rag_application.utils.exceptions import VectorStoreError

logger = logging.getLogger(__name__)


def _is_transient_query_error(error: Exception) -> bool:
    text = str(error).lower()
    transient_markers = (
        "getaddrinfo failed",
        "connection",
        "timed out",
        "timeout",
        "temporarily unavailable",
    )
    return any(marker in text for marker in transient_markers)


class PineconeVectorStore(VectorStoreInterface):
    def __init__(
        self,
        settings: Settings,
        dimension: int
    ):
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name

        if not self.pc.has_index(self.index_name):
            self.pc.create_index(
                name=self.index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            logger.info("Created Pinecone index: %s", self.index_name)

        self.index = self.pc.Index(self.index_name)

    def store_vectors(self, vector_data: List[Dict]) -> None:
        try:
            vectors = [
                {
                    "id": item["id"],
                    "values": item["vector"],
                    "metadata": item["metadata"]
                }
                for item in vector_data
            ]

            self.index.upsert(vectors=vectors)

            logger.info("Stored %d vectors", len(vectors))

        except Exception as e:
            logger.exception("Failed to store vectors")
            raise VectorStoreError(str(e)) from e

    def retrieve_vectors(
            self, 
            query_vector, 
            top_k: int = 5
    ):
        max_attempts = 3
        base_backoff_seconds = 1.5

        for attempt in range(1, max_attempts + 1):
            try:
                result = self.index.query(
                    vector=query_vector,
                    top_k=top_k,
                    include_metadata=True
                )

                logger.info(
                    "Retrieved %d matches",
                    len(result["matches"])
                )

                return result["matches"]

            except Exception as e:
                if (
                    attempt < max_attempts
                    and _is_transient_query_error(e)
                ):
                    wait_seconds = base_backoff_seconds * attempt
                    logger.warning(
                        "Query attempt %d/%d failed with transient error: %s. Retrying in %.1fs",
                        attempt,
                        max_attempts,
                        e,
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)
                    continue

                logger.exception("Query failed")
                raise VectorStoreError(str(e)) from e
        
    def delete_vectors(self, vector_ids: List[str]) -> None:
        try:
            self.index.delete(ids=vector_ids)
            logger.info("Deleted %d vectors", len(vector_ids))
        except Exception as e:
            logger.exception("Failed to delete vectors")
            raise VectorStoreError(str(e)) from e
    


VectorStore = PineconeVectorStore
