import logging
from typing import List

from rank_bm25 import BM25Okapi

from rag_application.ingestion.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class BM25Index:
    """
    BM25 lexical index built from DocumentChunk objects.

    This class is responsible for:
        - Building the BM25 index
        - Storing the original chunks
        - Searching using keyword matching
    """

    def __init__(
        self,
        documents: List[DocumentChunk]
    ):
        self.documents = documents

        logger.info(
            "Building BM25 index with %d chunks...",
            len(documents)
        )

        self.tokenized_documents = [
            self._tokenize(chunk.text)
            for chunk in documents
        ]

        self.bm25 = (
            BM25Okapi(self.tokenized_documents)
            if self.tokenized_documents
            else None
        )

        logger.info("BM25 index built successfully.")

    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[tuple[DocumentChunk, float]]:
        """
        Search the BM25 index.

        Returns:
            List of (DocumentChunk, score) tuples ordered by score.
        """

        if self.bm25 is None:
            logger.debug(
                "BM25 index is empty; returning no results for query '%s'",
                query
            )
            return []

        tokenized_query = self._tokenize(query)

        scores = self.bm25.get_scores(tokenized_query)

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )

        results = []

        for index in ranked_indices[:top_k]:

            score = float(scores[index])

            # Ignore zero-score results
            if score <= 0:
                continue

            results.append(
                (
                    self.documents[index],
                    score
                )
            )

        logger.debug(
            "BM25 retrieved %d chunks for query '%s'",
            len(results),
            query
        )

        return results

    @staticmethod
    def _tokenize(
        text: str
    ) -> List[str]:
        """
        Basic tokenizer.

        Lowercases and splits on whitespace.
        """

        return text.lower().split()
    
    def __len__(self) -> int:
        return len(self.documents)
    
    def is_empty(self) -> bool:
        return len(self.documents) == 0
    
    @property
    def size(self) -> int:
        return len(self.documents)
