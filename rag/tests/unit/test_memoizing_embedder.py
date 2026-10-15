from rag.embeddings.base import TextEmbedder
from rag.embeddings.memoizing import MemoizingEmbedder
from rag.observability import Stage, Tracer


class CountingEmbedder:
    model_name = "counting"

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.documents: list[list[str]] = []

    @property
    def dimension(self) -> int:
        return 2

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(text)), 1.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documents.append(list(texts))
        return [[0.0, 0.0] for _ in texts]


def test_satisfies_the_embedder_protocol():
    assert isinstance(MemoizingEmbedder(CountingEmbedder()), TextEmbedder)


def test_a_repeated_query_is_embedded_once():
    inner = CountingEmbedder()
    embedder = MemoizingEmbedder(inner)

    first = embedder.embed_query("what is sepsis")
    second = embedder.embed_query("what is sepsis")

    assert first == second
    assert inner.queries == ["what is sepsis"]


def test_the_memo_is_bounded_least_recently_used():
    inner = CountingEmbedder()
    embedder = MemoizingEmbedder(inner, max_entries=2)

    embedder.embed_query("a")
    embedder.embed_query("b")
    embedder.embed_query("a")  # refreshes "a"
    embedder.embed_query("c")  # evicts "b"
    embedder.embed_query("a")
    embedder.embed_query("b")

    assert inner.queries == ["a", "b", "c", "b"]


def test_callers_cannot_mutate_the_memoised_vector():
    embedder = MemoizingEmbedder(CountingEmbedder())

    embedder.embed_query("x").append(99.0)

    assert embedder.embed_query("x") == [1.0, 1.0]


def test_documents_pass_straight_through():
    inner = CountingEmbedder()
    embedder = MemoizingEmbedder(inner)

    embedder.embed_documents(["p1", "p2"])
    embedder.embed_documents(["p1", "p2"])

    assert inner.documents == [["p1", "p2"], ["p1", "p2"]]


def test_a_memo_hit_is_marked_on_the_open_span():
    from tests.unit.test_observability import RecordingRecorder

    recorder = RecordingRecorder()
    tracer = Tracer(recorder)
    embedder = MemoizingEmbedder(CountingEmbedder(), tracer=tracer)

    with tracer.trace():
        with tracer.span(Stage.QUERY_EMBEDDING):
            embedder.embed_query("q")
        with tracer.span(Stage.QUERY_EMBEDDING):
            embedder.embed_query("q")

    flags = [span.metadata["memoized"] for span in recorder.spans]
    assert flags == [False, True]
