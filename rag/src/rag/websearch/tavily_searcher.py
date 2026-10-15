import logging
from typing import Any

from rag.config.component_configs import WebSearchConfig
from rag.websearch.schemas import WebResult

logger = logging.getLogger(__name__)


class TavilySearcher:
    """
    Web search through Tavily (https://tavily.com).

    Tavily returns, for each page, the passage that matched the query rather
    than just a link, which is what a grounded answer needs as context.
    Restricted to `include_domains` when the config names any, so a medical
    answer is drawn from sources a student can trust rather than the whole
    web.
    """

    def __init__(
        self,
        config: WebSearchConfig,
        *,
        client: Any | None = None,
    ) -> None:
        if client is None:
            # Imported here, like the other provider SDKs, so importing the
            # engine does not require it when web search is switched off.
            from tavily import TavilyClient

            client = TavilyClient(api_key=config.api_key)

        self._client = client
        self.config = config

    def search(self, query: str) -> list[WebResult]:
        response = self._client.search(
            query,
            search_depth=self.config.search_depth,
            max_results=self.config.max_results,
            include_domains=list(self.config.include_domains) or None,
            timeout=self.config.timeout_seconds,
        )

        results: list[WebResult] = []

        for item in (response or {}).get("results", []):
            url = str(item.get("url") or "").strip()
            content = str(item.get("content") or "").strip()

            # A result with no page or no text gives the answer nothing to
            # stand on, and a source with no link cannot be checked.
            if not url or not content:
                continue

            results.append(
                WebResult(
                    title=str(item.get("title") or url).strip(),
                    url=url,
                    content=content,
                    score=float(item.get("score") or 0.0),
                )
            )

        logger.info("Web search returned %d usable result(s).", len(results))

        return results
