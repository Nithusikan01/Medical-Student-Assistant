from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pinecone import Pinecone, ServerlessSpec

from rag.config.settings import load_settings
from rag.ingestion.embedder import Embedder


def main():
    settings = load_settings()

    pc = Pinecone(api_key=settings.pinecone_api_key)

    index_name = settings.pinecone_index_name

    if pc.has_index(index_name):
        print(f"Deleting index '{index_name}'...")
        pc.delete_index(index_name)

    embedder = Embedder(settings.embedding_config())

    print(f"Creating index '{index_name}'...")

    pc.create_index(
        name=index_name,
        dimension=embedder.dimension,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1",
        ),
    )

    print("✓ Fresh Pinecone index created.")


if __name__ == "__main__":
    main()