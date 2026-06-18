from rag_application.retrieval.schemas import RetrievedChunk


def test_retrieved_chunk_creation():
    chunk = RetrievedChunk(
        id="chunk_1",
        score=0.95,
        text="Sample chunk text"
    )

    assert chunk.id == "chunk_1"
    assert chunk.score == 0.95
    assert chunk.text == "Sample chunk text"