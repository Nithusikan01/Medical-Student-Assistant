from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebResult:
    """One page a web search returned, with the passage it matched."""

    title: str
    url: str
    content: str
    score: float = 0.0
