from typing import Protocol, runtime_checkable

from rag.retrieval.schemas import RetrievedChunk


@runtime_checkable
class BaseRetriever(Protocol):
    """
    Anything that ranks chunks for a query.

    A Protocol, like every other seam in the engine (TextEmbedder,
    TextGenerator, ChunkSink, ConversationStore): an implementation
    satisfies it by shape, so a stub or a competing retriever needs no
    import of this module and no base class.
    """

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query: User query.
            top_k: Number of chunks to return. If None, the retriever
                should use its configured default.

        Returns:
            A list of RetrievedChunk objects ordered by decreasing relevance.
        """
        ...
