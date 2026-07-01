from dotenv import load_dotenv

from rag_application.config.settings import load_settings
from rag_application.vectorstore.pinecone_store import PineconeVectorStore
from rag_application.retrieval.retriever import Retriever
from rag_application.llm.generator import GeminiGenerator
from rag_application.services.rag_service import RAGService
from sentence_transformers import SentenceTransformer


def main():

    load_dotenv()
    settings = load_settings()

    # Models
    embedding_model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    dimension = len(embedding_model.encode("test"))

    # Vector store
    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=dimension
    )

    # Retriever
    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedding_model
    )

    # Generator
    generator = GeminiGenerator()

    # RAG system
    rag = RAGService(
        retriever=retriever,
        generator=generator
    )

    # Ask question
    question = "Who is Nithusikan?"

    answer = rag.answer(question)

    print("\n🔥 ANSWER:\n")
    print(answer)


if __name__ == "__main__":
    main()
