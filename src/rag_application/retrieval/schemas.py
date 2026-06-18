from dataclasses import dataclass

@dataclass
class RetrievedChunk:
    id: str
    score: float
    text: str
    metadata: dict