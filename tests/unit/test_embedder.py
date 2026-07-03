from unittest.mock import MagicMock
import numpy as np

from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.schemas import DocumentChunk


def test_embed():

    embedder = Embedder.__new__(Embedder)
    embedder.model = MagicMock()
    embedder.model.encode.return_value = np.array([
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6]
    ])

    chunks = [
        DocumentChunk(
            id="chunk_0",
            text="Hello world",
            source="test",
            chunk_index=0,
        ),
        DocumentChunk(
            id="chunk_1",
            text="Goodbye world",
            source="test",
            chunk_index=1,
        ),
    ]

    result = embedder.embed(chunks)

    assert len(result) == 2
    embedder.model.encode.assert_called_once_with(
        ["Hello world", "Goodbye world"]
    )
