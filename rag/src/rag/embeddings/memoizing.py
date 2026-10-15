"""
Query embeddings computed once per request rather than once per caller.

The semantic response cache and dense retrieval both embed the standalone
query. That used to be avoided by handing the cache's vector to retrieval
through a `query_embedding` parameter on every retriever - a cache
optimisation that leaked into BM25, the fusion layer and the query service,
and that silently assumed the cache and retrieval used the same model.

Sharing one memoizing embedder between them makes the saving a property of
the wiring instead: same embedder by construction, no parameter anywhere.
"""

import logging
import threading
from collections import OrderedDict

from rag.embeddings.base import TextEmbedder
from rag.observability import Tracer

logger = logging.getLogger(__name__)


class MemoizingEmbedder:
    """
    Wraps a TextEmbedder and remembers its most recent query vectors.

    Only queries are memoised: documents are embedded once, at ingestion,
    and never twice. Bounded LRU, thread-safe, and the wrapped call happens
    outside the lock so a slow hosted request never blocks other workers.
    """

    def __init__(
        self,
        inner: TextEmbedder,
        max_entries: int = 256,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self.inner = inner
        self.max_entries = max_entries
        self.tracer = tracer if tracer is not None else Tracer()

        self._lock = threading.Lock()
        self._vectors: OrderedDict[str, list[float]] = OrderedDict()

    @property
    def dimension(self) -> int:
        return self.inner.dimension

    @property
    def model_name(self) -> str | None:
        return getattr(self.inner, "model_name", None)

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            vector = self._vectors.get(text)

            if vector is not None:
                self._vectors.move_to_end(text)

        # Recorded on whichever span is open (query_embedding under dense
        # retrieval), so a near-zero embedding time is explained rather
        # than looking like a measurement error.
        self.tracer.annotate(memoized=vector is not None)

        if vector is not None:
            return list(vector)

        vector = self.inner.embed_query(text)

        if self.max_entries > 0:
            with self._lock:
                self._vectors[text] = list(vector)
                self._vectors.move_to_end(text)

                while len(self._vectors) > self.max_entries:
                    self._vectors.popitem(last=False)

        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)
