from dataclasses import asdict, dataclass, fields
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
    end_page_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert metadata into Pinecone-compatible metadata.

        Pinecone does not accept null metadata values, so optional
        fields with None values are omitted.
        """
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_dict(
        cls,
        metadata: dict[str, Any],
    ) -> "VectorRecordMetadata":
        """
        Build from stored metadata, ignoring keys this version does not know.

        Vectors outlive the code that wrote them: every vector upserted
        before section_title, heading_level and language were removed still
        carries some of them, and passing those through as keyword
        arguments would fail every query that matched one.
        """

        known = {name: metadata[name] for name in _FIELDS if name in metadata}

        return cls(**known)


_FIELDS = tuple(f.name for f in fields(VectorRecordMetadata))


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
