from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """
    Token accounting for one generation call, as reported by the provider.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """
    Response returned by an LLM.
    """

    text: str

    model: str | None = None

    latency: float | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    # None when the provider's response didn't carry usage data (shouldn't
    # happen for Gemini/Groq in practice, but a generator is free to omit it
    # rather than fabricate numbers).
    usage: TokenUsage | None = None
