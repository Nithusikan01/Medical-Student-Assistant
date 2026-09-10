import logging
from typing import List

from rag_application.ingestion.schemas import EmbeddedChunk
from rag_application.vectorstore.schemas import (
    VectorRecord,
    VectorRecordMetadata,
)

logger = logging.getLogger(__name__)

class VectorDataProcessor:

    def prepare(
        self,
        embedded_chunks: List[EmbeddedChunk],
    ) -> List[VectorRecord]:

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
                        section_title=chunk.metadata.section_title,
                        heading_level=chunk.metadata.heading_level,
                        chunk_index=chunk.chunk_index,
                        language=chunk.metadata.language,
                    ),
                )
            )
    
        logger.info("Prepared %d vector records.", len(records))
        return records