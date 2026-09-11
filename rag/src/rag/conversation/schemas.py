from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: int | None = None
