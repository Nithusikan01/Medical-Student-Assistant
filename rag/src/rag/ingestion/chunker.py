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

        chunks = list(self.iter_chunks(document))

        logger.info(
            "Created %d chunks from %d pages.",
            len(chunks),
            len(document.pages),
        )

        return chunks

    def iter_chunks(
        self,
        document: LoadedDocument,
    ) -> Iterator[DocumentChunk]:
        """
        Split the document page by page, yielding chunks as they are made.

        Chunks do not cross page boundaries, so every chunk has exactly one
        page number to cite.
        """

        global_chunk_index = 0

        for page in document.pages:

            for chunk_text in self.splitter.split_text(page.text):

                yield DocumentChunk(
                    id=f"{document.document_id}_chunk_{global_chunk_index}",
                    chunk_index=global_chunk_index,
                    text=chunk_text,
                    metadata=ChunkMetadata(
                        document_id=document.document_id,
                        filename=document.filename,
                        source_path=document.source_path,
                        page_number=page.page_number,
                        chunk_size=len(chunk_text),
                        overlap_size=self.config.chunk_overlap,
                    ),
                )

                global_chunk_index += 1

    def chunk_batches(
        self,
        document: LoadedDocument,
        batch_size: int = 100,
    ) -> Iterator[list[DocumentChunk]]:
        """
        Yield batches of at most `batch_size` chunks.

        Lazy: a page is split only when the batch that needs it is pulled,
        so the first batch is embedded while later pages are still unsplit,
        rather than after the whole document has been chunked up front.
        """

        batch: list[DocumentChunk] = []
        total = 0

        for chunk in self.iter_chunks(document):

            batch.append(chunk)

            if len(batch) == batch_size:
                total += len(batch)
                yield batch
                batch = []

        if batch:
            total += len(batch)
            yield batch

        logger.info(
            "Created %d chunks from %d pages.",
            total,
            len(document.pages),
        )


def _build_splitter(
    chunk_size: int,
    chunk_overlap: int,
):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
