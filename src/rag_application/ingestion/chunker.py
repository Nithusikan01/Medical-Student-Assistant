from typing import List
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag_application.config.component_configs import ChunkingConfig
from rag_application.ingestion.schemas import DocumentChunk
import time

logger = logging.getLogger(__name__)


class TextChunker:

    def __init__(self, config: ChunkingConfig):
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

    def chunk(self, pages: List[str], source: str) -> List[DocumentChunk]:

        text = "\n".join(pages)

        raw_chunks = self.splitter.split_text(text)

        timestamp = int(time.time())

        chunks: List[DocumentChunk] = []

        for i, chunk_text in enumerate(raw_chunks):
            chunks.append(
                DocumentChunk(
                    id=f"{source}_chunk_{i}",
                    text=chunk_text,
                    source=source,
                    chunk_index=i,
                    timestamp=timestamp
                )
            )

        logger.info(
            "Created %d structured chunks from %d pages",
            len(chunks),
            len(pages)
        )

        return chunks