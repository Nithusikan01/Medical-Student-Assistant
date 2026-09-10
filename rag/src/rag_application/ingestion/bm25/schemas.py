"""
Schemas for the BM25 corpus.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from rag_application.ingestion.schemas import DocumentChunk


class BM25Metadata(BaseModel):
    document_id: str
    filename: str
    source_path: str
    chunk_index: int
    page_number: int | None = None
    section_title: str | None = None
    heading_level: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    chunk_size: int = 0
    overlap_size: int = 0
    element_id: str | None = None
    element_type: str | None = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)


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
                section_title=metadata.section_title,
                heading_level=metadata.heading_level,
                start_char=metadata.start_char,
                end_char=metadata.end_char,
                chunk_size=metadata.chunk_size,
                overlap_size=metadata.overlap_size,
                element_id=metadata.element_id,
                element_type=metadata.element_type,
                language=metadata.language,
                tags=metadata.tags,
            ),
        )
