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
        """
        Convert metadata into Pinecone-compatible metadata.

        Pinecone does not accept null metadata values, so optional
        fields with None values are omitted.
        """
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }

    @classmethod
    def from_dict(
        cls,
        metadata: dict[str, Any],
    ) -> "VectorRecordMetadata":
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