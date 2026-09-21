"""
The response cache on its own.

Two things are being checked here, and they pull in opposite directions:
that a question asked again - or asked differently - is recognised, and
that one which only looks similar is not. A cache that serves the wrong
answer is worse than no cache at all, so most of these are about what it
refuses to match.
"""

import pytest

from rag.cache.keys import normalize_question, question_hash
from rag.cache.schemas import MATCH_EXACT, MATCH_MISS, MATCH_SEMANTIC
from rag.cache.semantic_cache import InMemorySemanticCache, NullResponseCache
from rag.config.component_configs import CacheConfig
from tests.unit.helpers import make_retrieved_chunk


class StubEmbedder:
    """
    Hands back whatever vector the test registered for a question.

    Not a real model: these tests are about the threshold and the scoping,
    and a real embedder would make "which questions are 0.96 apart" a
    property of the model rather than of the test.
    """

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[str] = []

    @property
    def dimension(self) -> int:
        return 3

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)

        return self.vectors[text]

    def embed_batch(self, chunks):  # pragma: no cover - never used here
        raise NotImplementedError


class ExplodingEmbedder:
    @property
    def dimension(self) -> int:
        return 3

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("the embedding service is down")

    def embed_batch(self, chunks):  # pragma: no cover - never used here
        raise NotImplementedError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


CHUNKS = [make_retrieved_chunk(chunk_id="doc_chunk_0", text="Paracetamol 1g.")]


def build_cache(embedder=None, **overrides) -> InMemorySemanticCache:
    overrides.setdefault("semantic_enabled", embedder is not None)

    return InMemorySemanticCache(CacheConfig(**overrides), embedder)


def store(cache, query="What is the dose?", *, answer="1g", top_k=5, model_id="m"):
    cache.store(
        query=query,
        top_k=top_k,
        model_id=model_id,
        answer=answer,
        chunks=CHUNKS,
    )


# ----------------------------------------------------------------------
# Normalising the question
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("What is the dose?", "what is the dose"),
        ("  what   is the dose  ", "what is the dose"),
        ("WHAT IS THE DOSE!!", "what is the dose"),
    ],
)
def test_differences_that_cannot_change_the_answer_are_erased(left, right):
    assert normalize_question(left) == normalize_question(right)
    assert question_hash(left) == question_hash(right)


def test_differences_that_can_change_the_answer_are_kept():
    assert question_hash("what is the dose") != question_hash("what is not the dose")


# ----------------------------------------------------------------------
# The exact tier
# ----------------------------------------------------------------------


def test_the_same_question_asked_again_is_a_hit():
    cache = build_cache()
    store(cache)

    lookup = cache.lookup(query="what is the dose", top_k=5, model_id="m")

    assert lookup.hit
    assert lookup.match == MATCH_EXACT
    assert lookup.entry.answer == "1g"
    assert lookup.entry.chunks == CHUNKS


def test_a_question_never_asked_is_a_miss():
    cache = build_cache()
    store(cache)

    lookup = cache.lookup(query="what is the half life", top_k=5, model_id="m")

    assert not lookup.hit
    assert lookup.match == MATCH_MISS
    assert lookup.entry is None


def test_a_different_top_k_does_not_share_an_entry():
    cache = build_cache()
    store(cache, top_k=5)

    assert not cache.lookup(query="What is the dose?", top_k=8, model_id="m").hit


def test_a_different_model_does_not_share_an_entry():
    cache = build_cache()
    store(cache, model_id="gemini-flash")

    assert not cache.lookup(
        query="What is the dose?",
        top_k=5,
        model_id="groq-gpt-oss-20b",
    ).hit


def test_an_empty_answer_is_not_stored():
    cache = build_cache()

    cache.store(
        query="What is the dose?",
        top_k=5,
        model_id="m",
        answer="",
        chunks=[],
    )

    assert cache.stats().entries == 0


# ----------------------------------------------------------------------
# The semantic tier
# ----------------------------------------------------------------------


def test_a_rephrasing_is_matched_by_meaning():
    embedder = StubEmbedder(
        {
            "What is the dose?": [1.0, 0.0, 0.0],
            "what dose should be given": [0.99, 0.141, 0.0],
        }
    )
    cache = build_cache(embedder, similarity_threshold=0.95)
    store(cache)

    lookup = cache.lookup(
        query="what dose should be given",
        top_k=5,
        model_id="m",
    )

    assert lookup.hit
    assert lookup.match == MATCH_SEMANTIC
    assert lookup.similarity == pytest.approx(0.99, abs=1e-3)
    assert lookup.entry.answer == "1g"


def test_a_merely_similar_question_is_not_matched():
    embedder = StubEmbedder(
        {
            "What is the dose?": [1.0, 0.0, 0.0],
            "what is the paediatric dose": [0.8, 0.6, 0.0],
        }
    )
    cache = build_cache(embedder, similarity_threshold=0.95)
    store(cache)

    lookup = cache.lookup(
        query="what is the paediatric dose",
        top_k=5,
        model_id="m",
    )

    assert not lookup.hit
    assert lookup.match == MATCH_MISS


def test_a_semantic_miss_hands_back_the_embedding_it_paid_for():
    """
    The saving that makes the semantic tier affordable: dense retrieval
    reuses this vector instead of embedding the same text again.
    """

    embedder = StubEmbedder({"what is the dose": [1.0, 0.0, 0.0]})
    cache = build_cache(embedder)

    lookup = cache.lookup(query="what is the dose", top_k=5, model_id="m")

    assert not lookup.hit
    assert lookup.query_embedding == pytest.approx([1.0, 0.0, 0.0])


def test_semantic_matching_respects_the_scope():
    """
    Two questions can mean the same thing and still not be
    interchangeable, because they were asked of different models.
    """

    embedder = StubEmbedder(
        {
            "What is the dose?": [1.0, 0.0, 0.0],
            "what dose should be given": [1.0, 0.0, 0.0],
        }
    )
    cache = build_cache(embedder, similarity_threshold=0.95)
    store(cache, model_id="gemini-flash")

    assert not cache.lookup(
        query="what dose should be given",
        top_k=5,
        model_id="groq-gpt-oss-20b",
    ).hit

    assert cache.lookup(
        query="what dose should be given",
        top_k=5,
        model_id="gemini-flash",
    ).hit


def test_an_embedder_that_fails_costs_the_cache_not_the_answer():
    cache = build_cache(ExplodingEmbedder())
    store(cache)

    lookup = cache.lookup(query="what dose should be given", top_k=5, model_id="m")

    assert not lookup.hit
    assert lookup.query_embedding is None


def test_the_semantic_tier_can_be_switched_off():
    embedder = StubEmbedder({"what dose should be given": [1.0, 0.0, 0.0]})
    cache = build_cache(embedder, semantic_enabled=False)
    store(cache)

    assert not cache.lookup(
        query="what dose should be given",
        top_k=5,
        model_id="m",
    ).hit
    assert embedder.calls == []


# ----------------------------------------------------------------------
# Bounds
# ----------------------------------------------------------------------


def test_an_entry_expires():
    clock = FakeClock()
    cache = InMemorySemanticCache(CacheConfig(ttl_seconds=60), clock=clock)

    store(cache)
    clock.advance(61)

    assert not cache.lookup(query="What is the dose?", top_k=5, model_id="m").hit
    assert cache.stats().entries == 0


def test_a_zero_ttl_means_no_expiry():
    clock = FakeClock()
    cache = InMemorySemanticCache(CacheConfig(ttl_seconds=0), clock=clock)

    store(cache)
    clock.advance(10_000)

    assert cache.lookup(query="What is the dose?", top_k=5, model_id="m").hit


def test_the_least_recently_used_entry_is_evicted_first():
    cache = build_cache(max_entries=2)

    store(cache, "question one")
    store(cache, "question two")

    # Reading "question one" makes "question two" the oldest.
    assert cache.lookup(query="question one", top_k=5, model_id="m").hit

    store(cache, "question three")

    assert cache.stats().entries == 2
    assert cache.lookup(query="question one", top_k=5, model_id="m").hit
    assert not cache.lookup(query="question two", top_k=5, model_id="m").hit
    assert cache.lookup(query="question three", top_k=5, model_id="m").hit


# ----------------------------------------------------------------------
# Correctness rules
# ----------------------------------------------------------------------


def test_an_answer_written_with_conversation_context_is_refused():
    cache = build_cache()

    cache.store(
        query="What is the dose?",
        top_k=5,
        model_id="m",
        answer="As I said above, 1g.",
        chunks=CHUNKS,
        context_free=False,
    )

    assert cache.stats().entries == 0
    assert not cache.lookup(query="What is the dose?", top_k=5, model_id="m").hit


def test_context_bearing_answers_can_be_allowed_in():
    cache = build_cache(store_context_free_only=False)

    cache.store(
        query="What is the dose?",
        top_k=5,
        model_id="m",
        answer="1g",
        chunks=CHUNKS,
        context_free=False,
    )

    assert cache.lookup(query="What is the dose?", top_k=5, model_id="m").hit


def test_a_corpus_change_empties_the_cache():
    """
    An answer is only as good as the documents it came from, and which
    entries a new document could have changed is not knowable without
    asking the questions again.
    """

    cache = build_cache()
    store(cache, "question one")
    store(cache, "question two")

    assert cache.invalidate() == 2
    assert cache.stats().entries == 0
    assert not cache.lookup(query="question one", top_k=5, model_id="m").hit


def test_a_disabled_cache_stores_and_returns_nothing():
    cache = build_cache(enabled=False)
    store(cache)

    assert cache.stats().entries == 0
    assert not cache.lookup(query="What is the dose?", top_k=5, model_id="m").hit


def test_the_null_cache_satisfies_the_same_contract():
    cache = NullResponseCache()

    cache.store(query="q", top_k=5, model_id="m", answer="a", chunks=CHUNKS)

    assert not cache.lookup(query="q", top_k=5, model_id="m").hit
    assert cache.invalidate() == 0
    assert cache.stats().entries == 0


# ----------------------------------------------------------------------
# Counters
# ----------------------------------------------------------------------


def test_stats_count_hits_by_how_they_were_matched():
    embedder = StubEmbedder(
        {
            "What is the dose?": [1.0, 0.0, 0.0],
            "what dose should be given": [1.0, 0.0, 0.0],
            "something else entirely": [0.0, 1.0, 0.0],
        }
    )
    cache = build_cache(embedder, similarity_threshold=0.95)
    store(cache)

    cache.lookup(query="what is the dose", top_k=5, model_id="m")
    cache.lookup(query="what dose should be given", top_k=5, model_id="m")
    cache.lookup(query="something else entirely", top_k=5, model_id="m")

    stats = cache.stats()

    assert stats.hits == 2
    assert stats.exact_hits == 1
    assert stats.semantic_hits == 1
    assert stats.misses == 1
    assert stats.stores == 1
    assert stats.entries == 1
