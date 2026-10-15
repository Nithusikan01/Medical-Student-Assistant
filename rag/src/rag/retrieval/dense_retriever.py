import logging

from rag.embeddings.base import TextEmbedder
from rag.observability import Stage, Tracer, summarize_scores
from rag.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)
from rag.vectorstore.base import VectorStoreInterface

logger = logging.getLogger(__name__)


class DenseRetriever:
    """
    Dense vector retriever using embedding similarity search.
    """

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding_model: TextEmbedder,
        *,
        default_top_k: int = 30,
        tracer: Tracer | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model

        # Used only when a caller passes no top_k. Taken here rather than
        # from a RetrievalConfig() built on the spot, which would silently
        # ignore whatever the deployment configured.
        self.default_top_k = default_top_k

        # Keyword-only and defaulted, so every existing call site - tests,
        # scripts, the factory - keeps working untouched. The default
        # records nothing.
        self.tracer = tracer if tracer is not None else Tracer()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks using dense vector search.
        """

        top_k = self.default_top_k if top_k is None else top_k

        with self.tracer.span(Stage.DENSE_RETRIEVAL, top_k=top_k) as span:

            # Nested rather than alongside, because embedding the query is
            # part of dense retrieval - keeping it separate is what lets the
            # timeline show whether the embedding call or the vector search
            # is the slow half. A memoizing embedder marks the span when the
            # vector was already computed (by the response cache).
            with self.tracer.span(
                Stage.QUERY_EMBEDDING,
                model=getattr(self.embedding_model, "model_name", None),
            ) as embedding_span:

                query_embedding = self.embedding_model.embed_query(query)

                embedding_span.set(dimension=len(query_embedding))

            matches = self.vector_store.query(
                embedding=query_embedding,
                top_k=top_k,
                filters=None,
            )

            if not matches:
                logger.warning("Dense retrieval found no matches.")

                span.set(result_count=0)

                return []

            retrieved_chunks: list[RetrievedChunk] = []
            skipped = 0

            for rank, match in enumerate(matches, start=1):
                metadata = match.metadata

                if metadata.text is None:
                    logger.warning(
                        "Skipping vector '%s' because text metadata is missing.",
                        match.id,
                    )

                    skipped += 1

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

            span.set(
                result_count=len(retrieved_chunks),
                skipped_count=skipped,
                **summarize_scores(chunk.score for chunk in retrieved_chunks),
            )

            return retrieved_chunks
