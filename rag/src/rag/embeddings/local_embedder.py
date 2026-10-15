import logging
from functools import cached_property

from rag.config.component_configs import EmbeddingConfig
from rag.utils.exceptions import EmbeddingError

logger = logging.getLogger(__name__)


class Embedder:
    """
    Embeddings from a local sentence-transformers model.

    Requires the rag package's "local-models" extra. The hosted
    PineconeEmbedder is the default; this one is for running without
    hosted inference.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self.model_name = config.model_name
        self.batch_size = config.batch_size

        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(self.model_name)

    @cached_property
    def dimension(self) -> int:
        """
        Vector width of the loaded model.

        Cached because determining it costs a full forward pass, and it
        cannot change for the life of the instance.
        """

        return int(self.model.encode("dimension_check").shape[0])

    def embed_query(self, text: str) -> list[float]:
        try:
            return self.model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).tolist()
        except Exception as exc:
            logger.exception("Failed to embed the query.")
            raise EmbeddingError("Failed to embed the query.") from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed passages for storage.

        Normalised like queries, so both sides of a comparison are unit
        vectors whatever metric the store uses.
        """

        if not texts:
            return []

        try:
            vectors = self.model.encode(
                texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as exc:
            logger.exception(
                "Failed to generate embeddings using model '%s'.",
                self.model_name,
            )
            raise EmbeddingError(
                f"Embedding generation failed using model '{self.model_name}'."
            ) from exc

        logger.info(
            "Generated %d embeddings (model='%s', batch_size=%d).",
            len(vectors),
            self.model_name,
            self.batch_size,
        )

        return [vector.tolist() for vector in vectors]
