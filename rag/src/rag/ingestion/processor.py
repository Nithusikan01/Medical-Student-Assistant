import logging

from rag.ingestion.schemas import EmbeddedChunk
from rag.vectorstore.schemas import (
    VectorRecord,
    VectorRecordMetadata,
)

logger = logging.getLogger(__name__)


class VectorDataProcessor:

    def prepare(
        self,
        embedded_chunks: list[EmbeddedChunk],
    ) -> list[VectorRecord]:

        records = []

        for chunk in embedded_chunks:

            records.append(
                VectorRecord(
                    id=chunk.id,
                    values=chunk.embedding,
                    metadata=VectorRecordMetadata(
                        document_id=chunk.metadata.document_id,
                        filename=chunk.metadata.filename,
                        source_path=chunk.metadata.source_path,
                        text=chunk.text,
                        page_number=chunk.metadata.page_number,
                        end_page_number=chunk.metadata.end_page_number,
                        chunk_index=chunk.chunk_index,
                    ),
                )
            )

        logger.info("Prepared %d vector records.", len(records))
        return records
