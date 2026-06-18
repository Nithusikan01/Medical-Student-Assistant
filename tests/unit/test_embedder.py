from unittest.mock import MagicMock
import numpy as np

from rag_application.ingestion.embedder import Embedder


def test_embed():

    embedder = Embedder.__new__(Embedder)
    embedder.model = MagicMock()
    embedder.model.encode.return_value = np.array([
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6]
    ])

    result = embedder.embed(
        ["Hello world", "Goodbye world"]
    )

    assert len(result) == 2
