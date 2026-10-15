from unittest.mock import MagicMock

import numpy as np

from rag.embeddings.base import TextEmbedder
from rag.embeddings.local_embedder import Embedder
from rag.embeddings.pinecone_embedder import PineconeEmbedder


def make_local_embedder() -> Embedder:
    embedder = Embedder.__new__(Embedder)
    embedder.model_name = "test-model"
    embedder.batch_size = 32
    embedder.model = MagicMock()
    return embedder


def test_embed_documents_returns_one_vector_per_text():
    embedder = make_local_embedder()
    embedder.model.encode.return_value = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
    )

    result = embedder.embed_documents(["Hello world", "Goodbye world"])

    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert embedder.model.encode.call_args.kwargs["normalize_embeddings"] is True


def test_embed_documents_with_nothing_to_embed_calls_no_model():
    embedder = make_local_embedder()

    assert embedder.embed_documents([]) == []
    embedder.model.encode.assert_not_called()


def test_both_embedders_satisfy_the_protocol():
    assert isinstance(make_local_embedder(), TextEmbedder)

    hosted = PineconeEmbedder.__new__(PineconeEmbedder)
    hosted._dimension = 1024
    assert isinstance(hosted, TextEmbedder)


def test_hosted_embedder_embeds_documents_as_passages_in_capped_batches():
    hosted = PineconeEmbedder.__new__(PineconeEmbedder)
    hosted.model_name = "m"
    hosted._dimension = 2
    hosted._client = MagicMock()

    def embed(model, inputs, parameters):
        response = MagicMock()
        response.data = [{"values": [1.0, 0.0]} for _ in inputs]
        return response

    hosted._client.inference.embed.side_effect = embed

    vectors = hosted.embed_documents([f"t{i}" for i in range(100)])

    assert len(vectors) == 100
    calls = hosted._client.inference.embed.call_args_list
    assert [len(c.kwargs["inputs"]) for c in calls] == [96, 4]
    assert all(c.kwargs["parameters"]["input_type"] == "passage" for c in calls)
