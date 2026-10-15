from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pinecone import Pinecone

from rag.config.settings import load_settings
from rag.vectorstore.pinecone_store import PineconeVectorStore


def embedding_dimension(settings) -> int:
    """
    The width the running application will embed at.

    Hosted inference is the default, and its model's dimension is
    configured; the local model only has to be loaded when it is the one in
    use. Sizing the index from the local model unconditionally created a
    384-wide index for a 1024-wide hosted embedder.
    """

    if settings.use_hosted_inference:
        return settings.hosted_embedding_dimension

    from rag.embeddings.local_embedder import Embedder

    return Embedder(settings.embedding_config()).dimension


def main():
    settings = load_settings()

    pc = Pinecone(api_key=settings.pinecone_api_key)

    index_name = settings.pinecone_index_name

    if pc.has_index(index_name):
        print(f"Deleting index '{index_name}'...")
        pc.delete_index(index_name)

    print(f"Creating index '{index_name}'...")

    PineconeVectorStore(
        config=settings.pinecone_config(),
        dimension=embedding_dimension(settings),
        client=pc,
    ).ensure_index()

    print("✓ Fresh Pinecone index created.")


if __name__ == "__main__":
    main()
