import logging
from functools import cached_property

from rag_application.config.component_configs import EmbeddingConfig
from rag_application.ingestion.schemas import (
    DocumentChunk,
    EmbeddedChunk,
)
from rag_application.utils.exceptions import EmbeddingError

logger = logging.getLogger(__name__)


class Embedder:
    """
    Generates vector embeddings for document chunks.
    """

    @cached_property
    def dimension(self) -> int:
        """
        Vector width of the loaded model.

        Cached because determining it costs a full forward pass, and it
        cannot change for the life of the instance.
        """

        return int(self.model.encode("dimension_check").shape[0])

    def __init__(self, config: EmbeddingConfig) -> None:
        self.model_name = config.model_name
        self.batch_size = config.batch_size

        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_name)

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a search query.

        Normalised here because the vector store uses cosine similarity.
        """

        return self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).tolist()

    def embed(
        self,
        chunk: DocumentChunk,
    ) -> EmbeddedChunk:
        """
        Generate an embedding for a single document chunk.
        """

        try:

            embedding = self.model.encode(
                chunk.text,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).tolist()

            embedded_chunk = EmbeddedChunk(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                metadata=chunk.metadata,
                embedding=embedding,
            )

            logger.debug(
                "Generated embedding for chunk '%s' (dimension=%d)",
                chunk.id,
                len(embedding),
            )

            return embedded_chunk

        except Exception as exc:

            logger.exception(
                "Failed to generate embedding for chunk '%s'.",
                chunk.id,
            )

            raise EmbeddingError(
                f"Failed to generate embedding for chunk '{chunk.id}'."
            ) from exc

    def embed_batch(
        self,
        chunks: list[DocumentChunk],
    ) -> list[EmbeddedChunk]:
        """
        Generate embeddings for a batch of document chunks.
        """

        if not chunks:
            logger.warning("No chunks provided for embedding.")
            return []

        try:

            texts = [chunk.text for chunk in chunks]

            vectors = self.model.encode(
                texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

            embedded_chunks = [
                self._to_embedded_chunk(chunk, vector.tolist())
                for chunk, vector in zip(chunks, vectors)
            ]

            logger.info(
                (
                    "Generated %d embeddings "
                    "(dimension=%d, model='%s', batch_size=%d)"
                ),
                len(embedded_chunks),
                len(embedded_chunks[0].embedding) if embedded_chunks else 0,
                self.model_name,
                self.batch_size,
            )

            return embedded_chunks

        except Exception as exc:

            logger.exception(
                "Failed to generate embeddings using model '%s'.",
                self.model_name,
            )

            raise EmbeddingError(
                f"Embedding generation failed using model '{self.model_name}'."
            ) from exc

    def _to_embedded_chunk(
        self,
        chunk: DocumentChunk,
        embedding: list[float],
    ) -> EmbeddedChunk:
        return EmbeddedChunk(
            id=chunk.id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            metadata=chunk.metadata,
            embedding=embedding,
        )
