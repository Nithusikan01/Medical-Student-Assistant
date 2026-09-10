from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: Optional[int] = None