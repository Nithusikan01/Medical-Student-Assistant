from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class VectorRecordMetadata:
    """
    Metadata stored alongside each embedding in the vector database.
    """

    document_id: str
    filename: str
    source_path: str

    text: str

    chunk_index: int

    page_number: int | None = None
    section_title: str | None = None
    heading_level: int | None = None

    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to a dictionary suitable for vector stores."""
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        metadata: dict[str, Any],
    ) -> "VectorRecordMetadata":
        """Create metadata from a vector store response."""
        return cls(**metadata)


@dataclass(slots=True)
class VectorRecord:
    """
    Represents a vector ready to be persisted in a vector database.
    """

    id: str
    values: list[float]
    metadata: VectorRecordMetadata


@dataclass(slots=True)
class SearchResult:
    """
    Represents a similarity search result returned by the vector database.
    """

    id: str
    score: float
    metadata: VectorRecordMetadata