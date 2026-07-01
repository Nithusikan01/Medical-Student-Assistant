from dataclasses import dataclass, field

@dataclass
class RetrievedChunk:
    id: str
    score: float
    text: str
    metadata: dict = field(default_factory=dict)
