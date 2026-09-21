"""
The value types a response cache stores and returns.

Kept apart from the implementation for the same reason every other stage of
the pipeline has its own dataclasses: what a cache lookup *found* is a
different thing from how it went looking.
"""

from dataclasses import dataclass, field

from rag.retrieval.schemas import RetrievedChunk

# How an entry was matched. Recorded on the telemetry span, so a hit rate
# can be split into "asked the same question again" and "asked it
# differently" - two findings that call for different responses.
MATCH_EXACT = "exact"
MATCH_SEMANTIC = "semantic"
MATCH_MISS = "miss"


@dataclass(frozen=True, slots=True)
class CacheScope:
    """
    What makes two questions the same question.

    `top_k` and `model_id` are part of identity rather than incidental:
    a different model legitimately gives a different answer, and a different
    top_k a different set of sources. Sharing entries across either would
    serve an answer to a question nobody asked.
    """

    query_hash: str
    top_k: int
    model_id: str

    @property
    def bucket(self) -> tuple[int, str]:
        """
        The scope minus the question itself.

        Semantic matching compares questions, so it may only ever compare
        entries that agree on everything else.
        """

        return (self.top_k, self.model_id)


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """
    One cached answer, with the sources it was generated from.

    The chunks are the engine's own `RetrievedChunk` objects rather than a
    serialised copy: they are frozen, and this cache lives in the process
    that produced them.
    """

    answer: str
    chunks: list[RetrievedChunk]
    standalone_query: str
    created_at: float
    embedding: list[float] | None = None


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """
    The result of a lookup, hit or miss.

    A miss is a value rather than `None` because a miss still carries
    something the caller wants: the query embedding the semantic tier just
    computed. Handing it back lets dense retrieval reuse it instead of
    embedding the same text a second time.
    """

    match: str = MATCH_MISS
    entry: CacheEntry | None = None
    similarity: float | None = None
    query_embedding: list[float] | None = None
    entry_count: int = 0

    @property
    def hit(self) -> bool:
        return self.entry is not None


@dataclass(frozen=True, slots=True)
class CacheStats:
    """
    Counters for the life of the process.

    Reported by `/api/monitoring` from telemetry spans rather than from
    here - these exist for tests and for a quick look from a script.
    """

    entries: int = 0
    max_entries: int = 0
    hits: int = 0
    misses: int = 0
    exact_hits: int = 0
    semantic_hits: int = 0
    stores: int = 0
    invalidations: int = 0
    extra: dict[str, int] = field(default_factory=dict)
