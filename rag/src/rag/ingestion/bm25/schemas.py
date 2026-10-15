"""
Schemas for the BM25 corpus.
"""

from __future__ import annotations

from pydantic import BaseModel

from rag.ingestion.schemas import DocumentChunk


class BM25Metadata(BaseModel):
    document_id: str
    filename: str
    source_path: str
    chunk_index: int
    page_number: int | None = None
    end_page_number: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    chunk_size: int = 0
    overlap_size: int = 0


class BM25CorpusRecord(BaseModel):
    id: str
    text: str
    metadata: BM25Metadata

    @classmethod
    def from_chunk(
        cls,
        chunk: DocumentChunk,
    ) -> BM25CorpusRecord:
        """
        Create a BM25 corpus record from a DocumentChunk.
        """
        metadata = chunk.metadata

        return cls(
            id=chunk.id,
            text=chunk.text,
            metadata=BM25Metadata(
                document_id=metadata.document_id,
                filename=metadata.filename,
                source_path=metadata.source_path,
                chunk_index=chunk.chunk_index,
                page_number=metadata.page_number,
                end_page_number=metadata.end_page_number,
                start_char=metadata.start_char,
                end_char=metadata.end_char,
                chunk_size=metadata.chunk_size,
                overlap_size=metadata.overlap_size,
            ),
        )
