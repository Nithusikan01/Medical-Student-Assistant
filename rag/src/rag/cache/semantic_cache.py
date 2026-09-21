import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

import numpy as np

from rag.cache.keys import normalize_question, scope_for
from rag.cache.schemas import (
    MATCH_EXACT,
    MATCH_SEMANTIC,
    CacheEntry,
    CacheLookup,
    CacheScope,
    CacheStats,
)
from rag.config.component_configs import CacheConfig
from rag.embeddings.base import TextEmbedder
from rag.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class NullResponseCache:
    """
    A cache that remembers nothing.

    What the factory wires up when caching is switched off, so the service
    has one code path instead of a truthiness check around every call.
    """

    def lookup(self, *, query: str, top_k: int, model_id: str) -> CacheLookup:
        return CacheLookup()

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
        return None

    def invalidate(self) -> int:
        return 0

    def stats(self) -> CacheStats:
        return CacheStats()


class InMemorySemanticCache:
    """
    Recently answered questions, matched exactly or by meaning.

    Two tiers, cheapest first:

      1. Exact - the normalised question hashed and looked up in a dict.
         Free, and the common case for a class of students working through
         the same material.
      2. Semantic - the question embedded and compared by cosine against
         every entry in the same scope. Costs one embedding call, which is
         handed back on a miss so dense retrieval does not pay for it
         twice.

    Bounded by entry count and by age, and evicted least-recently-used, so
    a long-running process cannot grow without limit. Everything is held in
    this process: two workers keep two caches and a restart keeps none,
    which is the trade accepted for needing no new infrastructure. The
    ResponseCache protocol is the seam for changing that later.

    Nothing here raises. A cache that fails is a cache miss.
    """

    def __init__(
        self,
        config: CacheConfig,
        embedder: TextEmbedder | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._embedder = embedder
        self._clock = clock

        self._lock = threading.Lock()
        self._entries: OrderedDict[CacheScope, CacheEntry] = OrderedDict()

        # Stacked unit vectors for the semantic tier, rebuilt lazily and
        # dropped on every mutation. Scanning a few hundred entries is one
        # matrix multiply; rebuilding it per lookup would not be.
        self._matrix: np.ndarray | None = None
        self._matrix_scopes: list[CacheScope] = []

        self._hits = 0
        self._misses = 0
        self._exact_hits = 0
        self._semantic_hits = 0
        self._stores = 0
        self._invalidations = 0
        self._expired = 0
        self._evicted = 0
        self._rejected = 0

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def lookup(
        self,
        *,
        query: str,
        top_k: int,
        model_id: str,
    ) -> CacheLookup:
        if not self._config.enabled:
            return CacheLookup()

        try:
            scope = scope_for(query=query, top_k=top_k, model_id=model_id)
        except Exception:
            logger.exception("Failed to build a response cache key.")
            return CacheLookup()

        with self._lock:
            self._drop_expired()

            entry = self._entries.get(scope)

            if entry is not None:
                self._entries.move_to_end(scope)
                self._hits += 1
                self._exact_hits += 1

                return CacheLookup(
                    match=MATCH_EXACT,
                    entry=entry,
                    similarity=1.0,
                    query_embedding=entry.embedding,
                    entry_count=len(self._entries),
                )

            has_candidates = bool(self._entries)
            entry_count = len(self._entries)

        if not self._config.semantic_enabled or self._embedder is None:
            return self._miss(entry_count=entry_count)

        # Outside the lock on purpose: with hosted inference this is a
        # network call, and holding the lock across it would serialise
        # every other request in the worker pool behind it.
        embedding = self._embed(query)

        if embedding is None:
            return self._miss(entry_count=entry_count)

        if not has_candidates:
            return self._miss(entry_count=entry_count, embedding=embedding)

        with self._lock:
            match = self._nearest(embedding, bucket=(top_k, model_id))

            if match is None:
                self._misses += 1

                return CacheLookup(
                    query_embedding=embedding,
                    entry_count=len(self._entries),
                )

            matched_scope, similarity = match
            entry = self._entries[matched_scope]
            self._entries.move_to_end(matched_scope)

            self._hits += 1
            self._semantic_hits += 1

            logger.info(
                "Response cache matched a rephrasing (similarity=%.4f).",
                similarity,
            )

            return CacheLookup(
                match=MATCH_SEMANTIC,
                entry=entry,
                similarity=similarity,
                query_embedding=embedding,
                entry_count=len(self._entries),
            )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

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
        if not self._config.enabled or not answer:
            return

        if self._config.max_entries <= 0:
            return

        # The correctness rule, not a tuning knob: an answer written with
        # a conversation in front of it can refer back to that
        # conversation, and there is no way to tell from the text whether
        # this one did.
        if self._config.store_context_free_only and not context_free:
            with self._lock:
                self._rejected += 1
            return

        try:
            scope = scope_for(query=query, top_k=top_k, model_id=model_id)
        except Exception:
            logger.exception("Failed to build a response cache key.")
            return

        embedding = query_embedding

        if embedding is None and self._config.semantic_enabled:
            embedding = self._embed(query)

        entry = CacheEntry(
            answer=answer,
            chunks=list(chunks),
            standalone_query=normalize_question(query),
            created_at=self._clock(),
            embedding=self._unit(embedding),
        )

        with self._lock:
            self._entries[scope] = entry
            self._entries.move_to_end(scope)
            self._stores += 1

            while len(self._entries) > self._config.max_entries:
                self._entries.popitem(last=False)
                self._evicted += 1

            self._forget_matrix()

    def invalidate(self) -> int:
        with self._lock:
            dropped = len(self._entries)

            self._entries.clear()
            self._forget_matrix()
            self._invalidations += 1

        if dropped:
            logger.info(
                "Dropped %d cached response(s) after a corpus change.",
                dropped,
            )

        return dropped

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                entries=len(self._entries),
                max_entries=self._config.max_entries,
                hits=self._hits,
                misses=self._misses,
                exact_hits=self._exact_hits,
                semantic_hits=self._semantic_hits,
                stores=self._stores,
                invalidations=self._invalidations,
                extra={
                    "expired": self._expired,
                    "evicted": self._evicted,
                    "rejected": self._rejected,
                },
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _miss(
        self,
        *,
        entry_count: int,
        embedding: list[float] | None = None,
    ) -> CacheLookup:
        with self._lock:
            self._misses += 1

        return CacheLookup(query_embedding=embedding, entry_count=entry_count)

    def _embed(self, query: str) -> list[float] | None:
        if self._embedder is None:
            return None

        try:
            return self._unit(self._embedder.embed_query(query))
        except Exception:
            # A failed embedding costs this request its cache, not its
            # answer: retrieval will embed the query again on its own.
            logger.exception("Failed to embed a query for the response cache.")
            return None

    @staticmethod
    def _unit(embedding: list[float] | None) -> list[float] | None:
        """
        Normalise to unit length so a dot product is a cosine.

        The local Embedder already returns normalised vectors; hosted
        inference makes no such promise, and comparing unnormalised
        vectors against a similarity threshold would quietly measure
        magnitude instead of direction.
        """

        if not embedding:
            return None

        try:
            vector = np.asarray(embedding, dtype=np.float32)
            norm = float(np.linalg.norm(vector))

            if norm == 0.0:
                return None

            return (vector / norm).tolist()
        except Exception:
            logger.exception("Failed to normalise a response cache embedding.")
            return None

    def _forget_matrix(self) -> None:
        """
        Caller must hold the lock.
        """

        self._matrix = None
        self._matrix_scopes = []

    def _drop_expired(self) -> None:
        """
        Caller must hold the lock.
        """

        ttl = self._config.ttl_seconds

        if ttl <= 0:
            return

        cutoff = self._clock() - ttl

        stale = [
            scope for scope, entry in self._entries.items() if entry.created_at < cutoff
        ]

        for scope in stale:
            del self._entries[scope]
            self._expired += 1

        if stale:
            self._forget_matrix()

    def _ensure_matrix(self) -> None:
        """
        Caller must hold the lock.
        """

        if self._matrix is not None:
            return

        scopes: list[CacheScope] = []
        rows: list[list[float]] = []

        for scope, entry in self._entries.items():
            if entry.embedding is None:
                continue

            scopes.append(scope)
            rows.append(entry.embedding)

        self._matrix_scopes = scopes
        self._matrix = np.asarray(rows, dtype=np.float32) if rows else None

    def _nearest(
        self,
        embedding: list[float],
        *,
        bucket: tuple[int, str],
    ) -> tuple[CacheScope, float] | None:
        """
        Best entry above the threshold, within one scope bucket.

        Caller must hold the lock.
        """

        try:
            self._ensure_matrix()

            if self._matrix is None:
                return None

            similarities = self._matrix @ np.asarray(embedding, dtype=np.float32)

            best_scope: CacheScope | None = None
            best_score = self._config.similarity_threshold

            for scope, score in zip(self._matrix_scopes, similarities):
                # Only questions asked of the same model, for the same
                # number of sources, are comparable at all.
                if scope.bucket != bucket:
                    continue

                value = float(score)

                if value >= best_score:
                    best_scope = scope
                    best_score = value

            if best_scope is None:
                return None

            return best_scope, best_score
        except Exception:
            logger.exception("Failed to search the response cache.")
            return None
