import logging
from typing import Any

from rag.config.component_configs import RetrievalConfig
from rag.observability import Stage, Tracer, summarize_scores
from rag.retrieval.base import BaseRetriever
from rag.retrieval.schemas import (
    RetrievedChunk,
    RetrievedChunkMetadata,
)
from rag.vectorstore.base import VectorStoreInterface

logger = logging.getLogger(__name__)


class DenseRetriever(BaseRetriever):
    """
    Dense vector retriever using embedding similarity search.
    """

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        embedding_model: Any,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model

        # Keyword-only and defaulted, so every existing call site - tests,
        # scripts, the factory - keeps working untouched. The default
        # records nothing.
        self.tracer = tracer if tracer is not None else Tracer()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks using dense vector search.
        """

        top_k = RetrievalConfig().candidate_k if top_k is None else top_k

        logger.debug(
            "Running dense retrieval for query: %s",
            query,
        )

        with self.tracer.span(Stage.DENSE_RETRIEVAL, top_k=top_k) as span:

            # Nested rather than alongside, because embedding the query is
            # part of dense retrieval - keeping it separate is what lets the
            # timeline show whether the embedding call or the vector search
            # is the slow half.
            #
            # Skipped entirely when the caller supplies the vector, and no
            # span is emitted then: an absent stage means the work did not
            # happen, which is exactly what is being reported.
            if query_embedding is None:

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
                logger.warning(
                    "No dense retrieval matches found for query: %s",
                    query,
                )

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
