import pytest

pytest.importorskip("rank_bm25")

from rag.indexes.bm25_index import BM25Index
from tests.unit.helpers import make_chunk


def test_empty_bm25_index_returns_no_results():
    index = BM25Index(documents=[])

    assert index.is_empty()
    assert index.search("anything") == []


def test_bm25_index_returns_matching_chunks():
    chunks = [
        make_chunk(0, "hybrid retrieval uses lexical search"),
        make_chunk(1, "semantic vectors answer similar meaning"),
        make_chunk(2, "reranking improves retrieved context"),
    ]
    index = BM25Index(documents=chunks)

    results = index.search("lexical", top_k=1)

    assert len(results) == 1
    assert results[0][0] == chunks[0]
    assert results[0][1] > 0


# ----------------------------------------------------------------------
# Tokenisation: punctuation must not stick to the word
# ----------------------------------------------------------------------

# Padded with unrelated chunks on purpose: BM25Okapi gives a term found in
# half the corpus an IDF of zero, so a four-chunk corpus would score
# "sepsis" at nothing and test BM25's arithmetic instead of the tokenizer.
CLINICAL = [
    make_chunk(
        0, "Sepsis is a life-threatening organ dysfunction caused by infection."
    ),
    make_chunk(1, "Septic shock, a subset of sepsis, requires vasopressors."),
    make_chunk(2, "The heart is a muscular organ that pumps blood."),
    make_chunk(3, "Anaemia: a reduced haemoglobin concentration."),
    make_chunk(4, "Insulin lowers blood glucose."),
    make_chunk(5, "The nephron filters plasma in the kidney."),
    make_chunk(6, "Alveoli exchange oxygen and carbon dioxide."),
    make_chunk(7, "Platelets adhere at sites of vascular injury."),
]


def test_a_question_mark_does_not_hide_the_term_being_asked_about():
    # Split on whitespace alone, "sepsis?" matched nothing and this question
    # ranked the heart chunk first - on the word "is".
    results = BM25Index(CLINICAL).search("What is sepsis?", top_k=8)

    found = [chunk.id for chunk, _ in results]

    assert set(found[:2]) == {"doc_chunk_0", "doc_chunk_1"}
    assert found.index("doc_chunk_1") < found.index("doc_chunk_2")


def test_punctuation_attached_in_the_text_still_matches():
    results = BM25Index(CLINICAL).search("Define anaemia", top_k=8)

    assert [chunk.id for chunk, _ in results][:1] == ["doc_chunk_3"]


def test_tokenisation_ignores_case_and_punctuation_on_both_sides():
    assert BM25Index._tokenize("Sepsis, (SEPSIS) sepsis?") == ["sepsis"] * 3


# ----------------------------------------------------------------------
# Which documents the index holds
# ----------------------------------------------------------------------


def test_the_index_reports_which_documents_it_holds():
    index = BM25Index(
        [
            make_chunk(0, "alpha", document_id="a"),
            make_chunk(1, "beta", document_id="a"),
            make_chunk(0, "gamma", document_id="b"),
        ]
    )

    assert index.document_ids == frozenset({"a", "b"})


def test_a_rebuild_replaces_the_document_set_with_the_index():
    index = BM25Index([make_chunk(0, "alpha", document_id="a")])

    index.rebuild([make_chunk(0, "beta", document_id="b")])

    assert index.document_ids == frozenset({"b"})
    assert BM25Index([]).document_ids == frozenset()
