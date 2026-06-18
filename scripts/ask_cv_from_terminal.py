from __future__ import annotations

import sys
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from rag_application.config.settings import load_settings
from rag_application.llm.generator import GeminiGenerator
from rag_application.retrieval.retriever import Retriever
from rag_application.services.rag_service import RAGService
from rag_application.vectorstore.pinecone_store import VectorStore


DEFAULT_QUESTION = "Who is the person in the CV?"


def main() -> int:
    load_dotenv()

    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION
    settings = load_settings()

    embedding_model = SentenceTransformer(settings.embedding_model_name)
    dimension = len(embedding_model.encode("dimension_check"))

    vector_store = VectorStore(settings=settings, dimension=dimension)
    retriever = Retriever(vector_store=vector_store, embedding_model=embedding_model)
    generator = GeminiGenerator(settings=settings)
    rag = RAGService(retriever=retriever, generator=generator)

    print(f"Q: {question}\n")
    print(rag.answer(question))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
