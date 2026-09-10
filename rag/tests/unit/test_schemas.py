from tests.unit.helpers import make_retrieved_chunk


def test_retrieved_chunk_creation():
    chunk = make_retrieved_chunk(
        chunk_id="chunk_1",
        text="Sample chunk text",
        score=0.95,
    )

    assert chunk.id == "chunk_1"
    assert chunk.score == 0.95
    assert chunk.text == "Sample chunk text"
    assert chunk.metadata.filename == "doc.pdf"
