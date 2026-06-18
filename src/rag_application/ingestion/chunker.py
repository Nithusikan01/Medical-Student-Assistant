from typing import List
import logging

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

from rag_application.config.component_configs import ChunkingConfig

logger = logging.getLogger(__name__)


class TextChunker:

    def __init__(
        self,
        config: ChunkingConfig
    ):
        self.chunk_size = config.chunk_size
        self.chunk_overlap = config.chunk_overlap

        self.splitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap
            )
        )

    def chunk(
        self,
        pages: List[str]
    ) -> List[str]:

        if not pages:
            raise ValueError(
                "No pages provided to chunk."
            )

        chunks = self.splitter.split_text(
            "\n".join(pages)
        )

        if not chunks:
            raise ValueError(
                "No chunks were created."
            )

        logger.info(
            "Created %d chunks from %d pages",
            len(chunks),
            len(pages)
        )

        return chunks