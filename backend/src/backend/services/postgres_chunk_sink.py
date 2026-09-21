import uuid
from typing import Self

import sqlalchemy as sa
from rag.ingestion.schemas import DocumentChunk
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Document, DocumentChunkRecord


class PostgresChunkSink:
    """
    Writes each ingested chunk into document_chunks.

    Rows accumulate across documents rather than replacing a single corpus
    file, which is what makes a multi-document library possible. Chunk rows
    for this document are cleared on entry so a retried ingest does not
    collide with a partial earlier attempt.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        document_id: uuid.UUID,
    ) -> None:
        self._session_factory = session_factory
        self.document_id = document_id
        self.count = 0

    def __enter__(self) -> Self:
        with self._session_factory() as session:
            session.execute(
                sa.delete(DocumentChunkRecord).where(
                    DocumentChunkRecord.document_id == self.document_id
                )
            )
            session.commit()

        self.count = 0

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is not None:
            # Leave nothing half-written behind; the caller marks the
            # document failed.
            with self._session_factory() as session:
                session.execute(
                    sa.delete(DocumentChunkRecord).where(
                        DocumentChunkRecord.document_id == self.document_id
                    )
                )
                session.commit()

        # Never suppress the original exception.
        return False

    def add_batch(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return

        with self._session_factory() as session:
            session.add_all(
                [
                    DocumentChunkRecord(
                        id=chunk.id,
                        document_id=self.document_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        page_number=chunk.metadata.page_number,
                        section_title=chunk.metadata.section_title,
                        heading_level=chunk.metadata.heading_level,
                        start_char=chunk.metadata.start_char,
                        end_char=chunk.metadata.end_char,
                        chunk_size=chunk.metadata.chunk_size,
                        overlap_size=chunk.metadata.overlap_size,
                        language=chunk.metadata.language,
                    )
                    for chunk in chunks
                ]
            )

            # Each landed batch is a sign of life. Without it, a stalled
            # ingestion is indistinguishable from a slow one: this loop
            # writes to document_chunks, so the documents row is otherwise
            # untouched for the whole run.
            session.execute(
                sa.update(Document)
                .where(Document.id == self.document_id)
                .values(heartbeat_at=sa.func.now())
            )

            session.commit()

        self.count += len(chunks)
