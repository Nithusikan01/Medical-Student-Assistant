from rag.config.component_configs import WebSearchConfig
from rag.websearch import WebSearcher
from rag.websearch.tavily_searcher import TavilySearcher


class FakeTavilyClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def search(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return self.response


def test_results_become_web_results_and_unusable_ones_are_dropped():
    client = FakeTavilyClient(
        {
            "results": [
                {
                    "title": "Sepsis",
                    "url": "https://medlineplus.gov/sepsis.html",
                    "content": "Sepsis is an extreme response to infection.",
                    "score": 0.83,
                },
                {"title": "No link", "url": "", "content": "text"},
                {"title": "No text", "url": "https://who.int/x", "content": "  "},
                {"url": "https://nhs.uk/conditions/sepsis/", "content": "Signs..."},
            ]
        }
    )

    results = TavilySearcher(WebSearchConfig(), client=client).search("sepsis")

    assert [r.url for r in results] == [
        "https://medlineplus.gov/sepsis.html",
        "https://nhs.uk/conditions/sepsis/",
    ]
    assert results[0].score == 0.83
    # A result with no title is cited by its address.
    assert results[1].title == "https://nhs.uk/conditions/sepsis/"


def test_the_search_is_restricted_and_bounded_by_the_config():
    client = FakeTavilyClient({"results": []})
    config = WebSearchConfig(
        max_results=3,
        search_depth="advanced",
        include_domains=("nih.gov", "who.int"),
        timeout_seconds=7.0,
    )

    TavilySearcher(config, client=client).search("metformin mechanism")

    (call,) = client.calls
    assert call["query"] == "metformin mechanism"
    assert call["max_results"] == 3
    assert call["search_depth"] == "advanced"
    assert call["include_domains"] == ["nih.gov", "who.int"]
    assert call["timeout"] == 7.0


def test_no_domains_searches_the_whole_web():
    client = FakeTavilyClient({"results": []})

    TavilySearcher(WebSearchConfig(include_domains=()), client=client).search("q")

    assert client.calls[0]["include_domains"] is None


def test_the_searcher_satisfies_the_protocol():
    searcher = TavilySearcher(WebSearchConfig(), client=FakeTavilyClient({}))

    assert isinstance(searcher, WebSearcher)
    assert searcher.search("q") == []
