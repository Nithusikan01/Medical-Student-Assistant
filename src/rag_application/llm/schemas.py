from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """
    Response returned by an LLM.
    """

    text: str

    model: str | None = None

    latency: float | None = None

    metadata: dict[str, Any] = field(default_factory=dict)