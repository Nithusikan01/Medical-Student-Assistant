"""
Schemas for the BM25 corpus.
"""

from __future__ import annotations

from pydantic import BaseModel

from rag_application.ingestion.schemas import DocumentChunk


class BM25Metadata(BaseModel):
    source: str
    chunk_index: int
    timestamp: int


class BM25CorpusRecord(BaseModel):
    id: str
    text: str
    metadata: BM25Metadata

    @classmethod
    def from_chunk(
        cls,
        chunk: DocumentChunk,
    ) -> "BM25CorpusRecord":
        """
        Create a BM25 corpus record from a DocumentChunk.
        """
        return cls(
            id=chunk.id,
            text=chunk.text,
            metadata=BM25Metadata(
                source=chunk.source,
                chunk_index=chunk.chunk_index,
                timestamp=chunk.timestamp,
            ),
        )