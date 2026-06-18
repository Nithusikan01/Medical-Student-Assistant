from dotenv import load_dotenv
import logging

from rag_application.config.settings import load_settings
from rag_application.ingestion.embedder import Embedder
from rag_application.retrieval.query_service import QueryService
from rag_application.retrieval.retriever import Retriever
from rag_application.vectorstore.pinecone_store import VectorStore


def main():
    load_dotenv()

    settings = load_settings()

    embedder = Embedder(settings.embedding_model_name)
    dimension = len(embedder.model.encode("test"))

    vector_store = VectorStore(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index_name,
        dimension=dimension
    )

    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedder
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
