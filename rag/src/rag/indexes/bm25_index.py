import logging
import re
from typing import NamedTuple

import numpy as np
from rank_bm25 import BM25Okapi

from rag.ingestion.schemas import DocumentChunk

logger = logging.getLogger(__name__)

# Runs of letters and digits. Punctuation separates tokens instead of
# sticking to them, so "sepsis?" and "sepsis." both match "sepsis", and
# "IL-6" splits into "il" + "6" identically in the documents and the query.
_TOKEN = re.compile(r"\w+")


class _IndexState(NamedTuple):
    documents: list[DocumentChunk]
    tokenized_documents: list[list[str]]
    bm25: BM25Okapi | None


class BM25Index:
    """
    BM25 lexical index built from DocumentChunk objects.

    This class is responsible for:
        - Building the BM25 index
        - Storing the original chunks
        - Searching using keyword matching
    """

    def __init__(self, documents: list[DocumentChunk]):
        self._state = self._build(documents)

    @staticmethod
    def _build(documents: list[DocumentChunk]) -> _IndexState:

        logger.info("Building BM25 index with %d chunks...", len(documents))

        tokenized = [BM25Index._tokenize(chunk.text) for chunk in documents]

        state = _IndexState(
            documents=documents,
            tokenized_documents=tokenized,
            bm25=BM25Okapi(tokenized) if tokenized else None,
        )

        logger.info("BM25 index built successfully.")

        return state

    def rebuild(
        self,
        documents: list[DocumentChunk],
    ) -> None:
        """
        Replace the index contents in place.

        The new state is built into a local first and then swapped in with a
        single attribute assignment, which is atomic in CPython. A search
        running concurrently in another worker therefore sees either the
        whole old index or the whole new one, never a half-rebuilt mixture,
        without needing a lock.
        """

        self._state = self._build(documents)

    # ------------------------------------------------------------------
    # Read-only views over the current state
    # ------------------------------------------------------------------

    @property
    def documents(self) -> list[DocumentChunk]:
        return self._state.documents

    @property
    def tokenized_documents(self) -> list[list[str]]:
        return self._state.tokenized_documents

    @property
    def bm25(self) -> BM25Okapi | None:
        return self._state.bm25

    def search(self, query: str, top_k: int = 5) -> list[tuple[DocumentChunk, float]]:
        """
        Search the BM25 index.

        Returns:
            List of (DocumentChunk, score) tuples ordered by score.
        """

        # Read once: a concurrent rebuild must not swap the index out from
        # under the scoring loop.
        state = self._state

        if state.bm25 is None:
            logger.debug(
                "BM25 index is empty; returning no results for query '%s'", query
            )
            return []

        tokenized_query = self._tokenize(query)

        if not tokenized_query or top_k <= 0:
            return []

        scores = np.asarray(state.bm25.get_scores(tokenized_query))

        # Only the top_k are ordered. Sorting every score in the corpus on
        # every query costs O(n log n) for results nobody asked for.
        k = min(top_k, len(scores))
        candidates = np.argpartition(-scores, k - 1)[:k]
        ranked_indices = candidates[np.argsort(-scores[candidates], kind="stable")]

        results = []

        for index in ranked_indices:

            score = float(scores[index])

            # Ignore zero-score results
            if score <= 0:
                continue

            results.append((state.documents[int(index)], score))

        logger.debug("BM25 retrieved %d chunks for query '%s'", len(results), query)

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        Case-folded runs of letters and digits.

        Splitting on whitespace alone kept punctuation attached, so the last
        word of nearly every question ("...of sepsis?") never matched the
        same word in the documents.
        """

        return _TOKEN.findall(text.casefold())

    def __len__(self) -> int:
        return len(self._state.documents)

    def is_empty(self) -> bool:
        return len(self._state.documents) == 0

    @property
    def size(self) -> int:
        return len(self._state.documents)
