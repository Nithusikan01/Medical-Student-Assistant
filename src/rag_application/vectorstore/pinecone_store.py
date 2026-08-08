import logging
import time

from pinecone import Pinecone, ServerlessSpec

from rag_application.config.settings import Settings
from rag_application.vectorstore.schemas import (
    SearchResult,
    VectorRecord,
    VectorRecordMetadata,
)
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
        dimension: int,
        batch_size: int = 100,
    ) -> None:

        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name
        self.batch_size = batch_size

        if not self.pc.has_index(self.index_name):

            self.pc.create_index(
                name=self.index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1",
                ),
            )

            logger.info(
                "Created Pinecone index '%s'.",
                self.index_name,
            )

        self.index = self.pc.Index(self.index_name)

    def upsert(
        self,
        records: list[VectorRecord],
    ) -> int:

        try:

            vectors = [
                {
                    "id": record.id,
                    "values": record.values,
                    "metadata": vars(record.metadata),
                }
                for record in records
            ]

            total = len(vectors)

            for start in range(0, total, self.batch_size):

                batch = vectors[start:start + self.batch_size]

                self.index.upsert(vectors=batch)

                logger.info(
                    "Uploaded vectors %d-%d.",
                    start + 1,
                    min(start + len(batch), total),
                )

            logger.info(
                "Successfully upserted %d vectors.",
                total,
            )

            return total

        except Exception as exc:

            logger.exception(
                "Failed to upsert vectors into Pinecone."
            )

            raise VectorStoreError(
                "Failed to upsert vectors."
            ) from exc

    def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[SearchResult]:

        max_attempts = 3
        base_backoff = 1.5

        for attempt in range(1, max_attempts + 1):

            try:

                response = self.index.query(
                    vector=embedding,
                    top_k=top_k,
                    filter=filters,
                    include_metadata=True,
                )

                results = []

                for match in response.matches:

                    metadata = match.metadata or {}

                    results.append(
                        SearchResult(
                            id=match.id,
                            score=match.score,
                            metadata=VectorRecordMetadata(**metadata),
                        )
                    )

                logger.info(
                    "Retrieved %d matches.",
                    len(results),
                )

                return results

            except Exception as exc:

                if (
                    attempt < max_attempts
                    and _is_transient_query_error(exc)
                ):

                    wait = base_backoff * attempt

                    logger.warning(
                        (
                            "Transient query failure "
                            "(attempt %d/%d). "
                            "Retrying in %.1f seconds."
                        ),
                        attempt,
                        max_attempts,
                        wait,
                    )

                    time.sleep(wait)
                    continue

                logger.exception(
                    "Vector query failed."
                )

                raise VectorStoreError(
                    "Failed to query Pinecone."
                ) from exc

        return []

    def delete(
        self,
        ids: list[str],
    ) -> int:

        try:

            self.index.delete(ids=ids)

            logger.info(
                "Deleted %d vectors.",
                len(ids),
            )

            return len(ids)

        except Exception as exc:

            logger.exception(
                "Failed to delete vectors."
            )

            raise VectorStoreError(
                "Failed to delete vectors."
            ) from exc

    def delete_all(self) -> None:
        """
        Delete every vector in the index.
        """

        try:

            self.index.delete(delete_all=True)

            logger.info(
                "Deleted all vectors from Pinecone index '%s'.",
                self.index_name,
            )

        except Exception as exc:

            logger.exception(
                "Failed to delete all vectors."
            )

            raise VectorStoreError(
                "Failed to delete all vectors."
            ) from exc

    def count(self) -> int:
        """
        Return the number of stored vectors.
        """

        try:

            stats = self.index.describe_index_stats()

            total = stats.total_vector_count

            logger.debug(
                "Pinecone contains %d vectors.",
                total,
            )

            return total

        except Exception as exc:

            logger.exception(
                "Failed to retrieve vector count."
            )

            raise VectorStoreError(
                "Failed to retrieve vector count."
            ) from exc


VectorStore = PineconeVectorStore