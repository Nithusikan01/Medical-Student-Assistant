from dotenv import load_dotenv
import logging

from rag_application.config.settings import load_settings
from rag_application.config.component_configs import EmbeddingConfig
from rag_application.ingestion.embedder import Embedder
from rag_application.retrieval.query_service import QueryService
from rag_application.retrieval.retriever import Retriever
from rag_application.vectorstore.pinecone_store import PineconeVectorStore


def main():
    load_dotenv()

    settings = load_settings()

    embedder = Embedder(
        config=EmbeddingConfig(
            model_name=settings.embedding_model_name,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
    )
    dimension = len(embedder.model.encode("test"))

    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=dimension
    )

    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedder.model
    )
    query_service = QueryService(retriever)

    results = query_service.search("Who is Nithusikan?")

    logging.getLogger(__name__).info("Retrieved %d results", len(results))

    for result in results:
        print(result.score)
        print(result.text)
        print()


if __name__ == "__main__":
    main()
