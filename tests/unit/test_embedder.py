from unittest.mock import MagicMock

import numpy as np

from rag_application.ingestion.embedder import Embedder

from tests.unit.helpers import make_chunk


def test_embed_single_chunk():
    embedder = Embedder.__new__(Embedder)
    embedder.model = MagicMock()
    embedder.model.encode.return_value = np.array([0.1, 0.2, 0.3])

    chunk = make_chunk(0, "Hello world")

    result = embedder.embed(chunk)

    assert result.id == chunk.id
    assert result.embedding == [0.1, 0.2, 0.3]
    embedder.model.encode.assert_called_once_with(
        "Hello world",
        show_progress_bar=False,
        convert_to_numpy=True,
    )


def test_embed_batch():
    embedder = Embedder.__new__(Embedder)
    embedder.model_name = "test-model"
    embedder.batch_size = 32
    embedder.model = MagicMock()
    embedder.model.encode.return_value = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
    )

    chunks = [
        make_chunk(0, "Hello world"),
        make_chunk(1, "Goodbye world"),
    ]

    result = embedder.embed_batch(chunks)

    assert len(result) == 2
    assert result[1].embedding == [0.4, 0.5, 0.6]
