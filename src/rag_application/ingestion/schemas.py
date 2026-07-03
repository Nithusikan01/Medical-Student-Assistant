from dataclasses import dataclass, field
from typing import Optional

@dataclass(slots=True)
class DocumentChunk:
    id: str
    text: str
    source: str
    chunk_index: int
    page_number: Optional[int] = None
    timestamp: int = 0
    metadata: dict = field(default_factory=dict)