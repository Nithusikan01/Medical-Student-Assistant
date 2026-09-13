import logging
from collections.abc import Iterator

from rag.config.component_configs import ChunkingConfig
from rag.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
    LoadedDocument,
)

logger = logging.getLogger(__name__)


class TextChunker:

    def __init__(self, config: ChunkingConfig):

        self.config = config

        self.splitter = _build_splitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

    def chunk(
        self,
        document: LoadedDocument,
    ) -> list[DocumentChunk]:

        chunks: list[DocumentChunk] = []

        global_chunk_index = 0

        for page in document.pages:

            raw_chunks = self.splitter.split_text(page.text)

            for page_chunk_index, chunk_text in enumerate(raw_chunks):

                metadata = ChunkMetadata(
                    document_id=document.document_id,
                    filename=document.filename,
                    source_path=document.source_path,
                    page_number=page.page_number,
                    chunk_size=len(chunk_text),
                    overlap_size=self.config.chunk_overlap,
                )

                chunks.append(
                    DocumentChunk(
                        id=f"{document.document_id}_chunk_{global_chunk_index}",
                        chunk_index=global_chunk_index,
                        text=chunk_text,
                        metadata=metadata,
                    )
                )

                global_chunk_index += 1

        logger.info(
            "Created %d chunks from %d pages.",
            len(chunks),
            len(document.pages),
        )

        return chunks

    def chunk_batches(
        self,
        document: LoadedDocument,
        batch_size: int = 100,
    ) -> Iterator[list[DocumentChunk]]:

        chunks = self.chunk(document)

        logger.info(
            "Yielding %d chunks in batches of %d.",
            len(chunks),
            batch_size,
        )

        for start in range(0, len(chunks), batch_size):

            end = min(start + batch_size, len(chunks))

            batch = chunks[start:end]

            logger.debug(
                "Yielding chunk batch %d-%d.",
                start,
                end - 1,
            )

            yield batch


def _build_splitter(
    chunk_size: int,
    chunk_overlap: int,
):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
