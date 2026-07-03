from typing import List
from rag_application.retrieval.schemas import RetrievedChunk


class CorpusStore:
    """
    Single source of truth for all chunks in system.

    Used by:
    - BM25Retriever
    - (optional) analytics
    """

    def __init__(self):
        self.chunks: List[RetrievedChunk] = []

    def add_chunks(self, chunks: List[RetrievedChunk]):
        self.chunks.extend(chunks)

    def get_all(self) -> List[RetrievedChunk]:
        return self.chunks