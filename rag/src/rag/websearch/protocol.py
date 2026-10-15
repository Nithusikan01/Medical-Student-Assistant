from typing import Protocol, runtime_checkable

from rag.websearch.schemas import WebResult


@runtime_checkable
class WebSearcher(Protocol):
    """
    Searches the web for passages that answer a query.

    The fallback the service turns to when the class library has nothing on
    a medical question. A Protocol like every other provider seam, so tests
    and other providers need no import of Tavily. Implementations raise on
    failure; the service decides what happens then.
    """

    def search(self, query: str) -> list[WebResult]: ...
