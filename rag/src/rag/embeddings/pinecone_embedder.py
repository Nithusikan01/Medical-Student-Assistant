import logging

from rag.config.component_configs import PineconeEmbeddingConfig
from rag.ingestion.schemas import DocumentChunk, EmbeddedChunk
from rag.utils.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

# Pinecone caps how many inputs one embed call accepts.
MAX_INPUTS_PER_CALL = 96


class PineconeEmbedder:
    """
    Embeddings from Pinecone's hosted inference API.

    Keeps no model weights locally, so the service starts in seconds and the
    deployed image carries neither PyTorch nor sentence-transformers.

    Documents and queries are embedded with different input types: these
    models are trained asymmetrically, and using "passage" for a query
    measurably degrades retrieval.
    """

    def __init__(self, config: PineconeEmbeddingConfig) -> None:
        from pinecone import Pinecone

        self._client = Pinecone(api_key=config.api_key)
        self.model_name = config.model_name
        self._dimension = config.dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []

        for start in range(0, len(texts), MAX_INPUTS_PER_CALL):
            batch = texts[start : start + MAX_INPUTS_PER_CALL]

            response = self._client.inference.embed(
                model=self.model_name,
                inputs=batch,
                parameters={"input_type": input_type, "truncate": "END"},
            )

            vectors.extend(list(item["values"]) for item in response.data)

        return vectors

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._embed([text], "query")[0]
        except Exception as exc:
            logger.exception("Failed to embed the query.")
            raise EmbeddingError("Failed to embed the query.") from exc

    def embed(self, chunk: DocumentChunk) -> EmbeddedChunk:
        return self.embed_batch([chunk])[0]

    def embed_batch(
        self,
        chunks: list[DocumentChunk],
    ) -> list[EmbeddedChunk]:
        if not chunks:
            logger.warning("No chunks provided for embedding.")
            return []

        try:
            vectors = self._embed([chunk.text for chunk in chunks], "passage")
        except Exception as exc:
            logger.exception(
                "Failed to generate embeddings using '%s'.",
                self.model_name,
            )
            raise EmbeddingError(
                f"Embedding generation failed using '{self.model_name}'."
            ) from exc

        logger.info(
            "Generated %d embeddings (model='%s', dimension=%d).",
            len(vectors),
            self.model_name,
            self._dimension,
        )

        return [
            EmbeddedChunk(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                metadata=chunk.metadata,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors)
        ]
