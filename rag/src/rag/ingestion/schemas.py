from dataclasses import dataclass, field

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
    # ---------- Document Information ----------
    document_id: str
    filename: str
    source_path: str

    # ---------- Location ----------
    page_number: int | None = None
    section_title: str | None = None
    heading_level: int | None = None

    # Position inside document
    start_char: int | None = None
    end_char: int | None = None

    # ---------- Chunk Information ----------
    chunk_size: int = 0
    overlap_size: int = 0

    # Parent element information
    element_id: str | None = None
    element_type: str | None = None

    # ---------- Retrieval ----------
    language: str = "en"

    # Used for filtering
    tags: list[str] = field(default_factory=list)


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
