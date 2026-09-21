from typing import Protocol, runtime_checkable

from rag.cache.schemas import CacheLookup, CacheStats
from rag.retrieval.schemas import RetrievedChunk


@runtime_checkable
class ResponseCache(Protocol):
    """
    Answers the engine may return without doing the work again.

    A protocol for the same reason ConversationStore and ChunkSink are:
    the in-process implementation shipped here is bounded by one process's
    memory, and an application that outgrows that supplies a shared store
    instead without the service knowing.

    Implementations must never raise. A cache that fails is a cache miss -
    it may cost a request its saving, but it may not cost it its answer.
    """

    def lookup(
        self,
        *,
        query: str,
        top_k: int,
        model_id: str,
    ) -> CacheLookup: ...

    def store(
        self,
        *,
        query: str,
        top_k: int,
        model_id: str,
        answer: str,
        chunks: list[RetrievedChunk],
        query_embedding: list[float] | None = None,
        context_free: bool = True,
    ) -> None:
        """
        Offer an answer for caching.

        `context_free` says whether the answer was generated with no
        conversation history in its prompt. An answer that had history can
        refer back to it, so handing it to a different conversation would
        be wrong; whether that rules the entry out is the implementation's
        policy, which is why the caller reports the fact rather than
        applying it.
        """
        ...

    def invalidate(self) -> int:
        """
        Drop everything, returning how many entries were dropped.

        Called when the corpus changes: an answer is only as good as the
        documents it was retrieved from, and working out which entries a
        newly ingested PDF could have changed is not knowable without
        asking the question again.
        """
        ...

    def stats(self) -> CacheStats: ...
