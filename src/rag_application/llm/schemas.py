from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class LLMResponse:
    text: str
    model: Optional[str] = None
    latency: Optional[float] = None
    metadata: Dict = field(default_factory=dict)