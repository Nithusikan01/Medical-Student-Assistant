from rag.indexes.bm25_index import BM25Index
from tests.unit.helpers import make_chunk

# BM25 gives a term that appears in every document a negative IDF, and search
# discards non-positive scores. A corpus therefore needs more than one
# document before any term is discriminative enough to match.
OTHER_DOCUMENTS = [
    make_chunk(1, "orthopedics bone fracture"),
    make_chunk(2, "dermatology skin rash"),
]


def test_rebuild_replaces_documents():
    index = BM25Index([make_chunk(0, "cardiology heart failure"), *OTHER_DOCUMENTS])

    assert index.search("cardiology")

    index.rebuild([make_chunk(0, "nephrology kidney function"), *OTHER_DOCUMENTS])

    assert index.size == 3
    assert index.search("nephrology")
    assert index.search("cardiology") == []


def test_rebuild_to_empty_disables_search():
    index = BM25Index([make_chunk(0, "cardiology heart failure")])

    index.rebuild([])

    assert index.is_empty()
    assert len(index) == 0
    assert index.search("cardiology") == []


def test_rebuild_from_empty_enables_search():
    index = BM25Index([])

    assert index.search("anything") == []

    index.rebuild([make_chunk(0, "cardiology heart failure"), *OTHER_DOCUMENTS])

    assert index.search("cardiology")


def test_single_document_corpus_matches_nothing():
    """
    Documents the consequence of BM25's IDF on a one-document corpus: every
    term is in every document, so nothing scores above zero and hybrid
    retrieval falls back to dense-only until a second document is ingested.
    """

    index = BM25Index([make_chunk(0, "cardiology heart failure")])

    assert index.search("cardiology") == []


def test_public_attributes_still_readable():
    chunks = [make_chunk(0, "one two"), make_chunk(1, "three four")]
    index = BM25Index(chunks)

    assert index.documents == chunks
    assert index.tokenized_documents == [["one", "two"], ["three", "four"]]
    assert index.bm25 is not None
