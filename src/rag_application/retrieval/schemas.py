from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    id: str
    score: float
    text: str
    metadata: dict = field(default_factory=dict)
    retrieval_method: str = ""