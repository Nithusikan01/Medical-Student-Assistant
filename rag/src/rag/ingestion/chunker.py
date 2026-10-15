import logging
from bisect import bisect_right
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
        Split the whole document's text, yielding chunks in order.

        Pages are joined with a single newline rather than split one by
        one. Splitting per page cut every paragraph that continued onto the
        next page into two fragments, neither of which a question could
        match on its own. A page break is joined with "\n" rather than a
        paragraph break because the splitter prefers to cut at paragraph
        breaks, and a page break is usually not one.

        Each chunk records the character range it covers and the pages it
        starts and ends on.
        """

        if not document.pages:
            return

        text, page_starts = _join_pages(document)

        cursor = 0
        previous_length = 0

        for index, chunk_text in enumerate(self.splitter.split_text(text)):

            start = _locate(
                text,
                chunk_text,
                # The splitter's own start-index logic: the next chunk begins
                # at most chunk_overlap characters before the previous end.
                hint=max(0, cursor + previous_length - self.config.chunk_overlap),
                floor=cursor,
            )

            if start is None:
                # Not expected - the splitter only strips and slices - but a
                # chunk with no offsets is better than no chunk.
                logger.warning("Could not locate chunk %d in the document text.", index)
                first_page = last_page = start_char = end_char = None
            else:
                start_char = start
                end_char = start + len(chunk_text)
                first_page = _page_at(page_starts, document, start_char)
                last_page = _page_at(page_starts, document, end_char - 1)
                cursor = start
                previous_length = len(chunk_text)

            yield DocumentChunk(
                id=f"{document.document_id}_chunk_{index}",
                chunk_index=index,
                text=chunk_text,
                metadata=ChunkMetadata(
                    document_id=document.document_id,
                    filename=document.filename,
                    source_path=document.source_path,
                    page_number=first_page,
                    end_page_number=last_page,
                    start_char=start_char,
                    end_char=end_char,
                    chunk_size=len(chunk_text),
                    overlap_size=self.config.chunk_overlap,
                ),
            )

    def chunk_batches(
        self,
        document: LoadedDocument,
        batch_size: int = 100,
    ) -> Iterator[list[DocumentChunk]]:
        """
        Yield batches of at most `batch_size` chunks.

        The text is split in one pass (chunks may span pages, so the splitter
        needs the whole document), but chunk objects are built only as each
        batch is pulled.
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


# What pages are joined with. Its length is part of every offset.
PAGE_SEPARATOR = "\n"


def _join_pages(document: LoadedDocument) -> tuple[str, list[int]]:
    """
    The document's text, and the offset at which each page starts in it.
    """

    starts: list[int] = []
    offset = 0

    for page in document.pages:
        starts.append(offset)
        offset += len(page.text) + len(PAGE_SEPARATOR)

    return PAGE_SEPARATOR.join(page.text for page in document.pages), starts


def _page_at(page_starts: list[int], document: LoadedDocument, offset: int) -> int:
    """
    The page number containing `offset`. A separator belongs to the page
    before it.
    """

    return document.pages[bisect_right(page_starts, offset) - 1].page_number


def _locate(text: str, chunk: str, *, hint: int, floor: int) -> int | None:
    """
    Where `chunk` starts in `text`, searching from `hint` and then from
    `floor` (the previous chunk's start, which no later chunk precedes).
    """

    for start_from in (hint, floor):
        found = text.find(chunk, start_from)

        if found != -1:
            return found

    return None


def _build_splitter(
    chunk_size: int,
    chunk_overlap: int,
):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
