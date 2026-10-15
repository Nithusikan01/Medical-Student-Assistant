from dataclasses import dataclass

# ------STAGE 1 -------


@dataclass(slots=True)
class LoadedPage:
    page_number: int
    text: str


@dataclass(slots=True)
class LoadedDocument:
    document_id: str
    filename: str
    source_path: str
    pages: list[LoadedPage]


# ------STAGE 2 -------


@dataclass(slots=True)
class ChunkMetadata:
    """
    Where a chunk came from. Every field is one the chunker actually fills.

    Section titles, heading levels, element ids, a language and tags used to
    be declared here and carried through every stage, the database and the
    API, while nothing ever set them: a PDF's extracted text has no
    structure to read them from. They were removed rather than left to
    look meaningful.
    """

    # ---------- Document Information ----------
    document_id: str
    filename: str
    source_path: str

    # ---------- Location ----------
    # The page the chunk starts on, and the page it ends on. Chunks are cut
    # from the whole document's text, so one can run across a page break.
    page_number: int | None = None
    end_page_number: int | None = None

    # Character offsets into the document's text, with pages joined by "\n".
    start_char: int | None = None
    end_char: int | None = None

    # ---------- Chunk Information ----------
    chunk_size: int = 0
    overlap_size: int = 0


@dataclass(slots=True)
class DocumentChunk:
    id: str  # Globally unique identifier
    chunk_index: int  # Position within the document
    text: str
    metadata: ChunkMetadata


# -----STAGE 3 -------


@dataclass(slots=True)
class EmbeddedChunk:
    id: str
    chunk_index: int
    text: str
    metadata: ChunkMetadata
    embedding: list[float]
