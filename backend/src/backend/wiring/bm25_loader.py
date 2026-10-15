import logging

import sqlalchemy as sa
from rag.ingestion.schemas import ChunkMetadata, DocumentChunk
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import STATUS_READY, Document, DocumentChunkRecord

logger = logging.getLogger(__name__)


def load_bm25_documents(
    session_factory: sessionmaker[Session],
) -> list[DocumentChunk]:
    """
    Load the lexical corpus from the document registry.

    Only ready documents contribute, so a document that is still processing,
    failed, or being deleted is never lexically retrievable.
    """

    with session_factory() as session:
        rows = session.execute(
            sa.select(DocumentChunkRecord, Document.filename)
            .join(Document, Document.id == DocumentChunkRecord.document_id)
            .where(Document.status == STATUS_READY)
            .order_by(
                DocumentChunkRecord.document_id,
                DocumentChunkRecord.chunk_index,
            )
        ).all()

    chunks = [
        DocumentChunk(
            id=record.id,
            chunk_index=record.chunk_index,
            text=record.text,
            metadata=ChunkMetadata(
                document_id=str(record.document_id),
                filename=filename,
                source_path="",
                page_number=record.page_number,
                end_page_number=record.end_page_number,
                start_char=record.start_char,
                end_char=record.end_char,
                chunk_size=record.chunk_size,
                overlap_size=record.overlap_size,
            ),
        )
        for record, filename in rows
    ]

    logger.info("Loaded %d BM25 chunks from the document registry.", len(chunks))

    return chunks
