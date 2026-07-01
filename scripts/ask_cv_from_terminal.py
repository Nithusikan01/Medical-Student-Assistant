from __future__ import annotations

import sys
import uuid

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from rag_application.config.component_configs import GenerationConfig
from rag_application.config.settings import load_settings
from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.summarizer import ConversationSummarizer
from rag_application.conversation.session_manager import SessionManager
from rag_application.llm.generator import GeminiGenerator
from rag_application.retrieval.retriever import Retriever
from rag_application.services.history_aware_rag_service import HistoryAwareRAGService
from rag_application.vectorstore.pinecone_store import PineconeVectorStore as VectorStore


DEFAULT_QUESTION = "Who is the person in the CV?"


def build_history_aware_rag() -> HistoryAwareRAGService:
    settings = load_settings()

    embedding_model = SentenceTransformer(settings.embedding_model_name)
    dimension = len(embedding_model.encode("dimension_check"))

    vector_store = VectorStore(settings=settings, dimension=dimension)
    retriever = Retriever(vector_store=vector_store, embedding_model=embedding_model)

    generator = GeminiGenerator(
        config=GenerationConfig(
            model_name=settings.generation_model_name,
            api_key=settings.gemini_api_key,
        )
    )

    session_manager = SessionManager()
    query_rewriter = QueryRewriter(generator=generator)
    summarizer = ConversationSummarizer(generator=generator)

    return HistoryAwareRAGService(
        retriever=retriever,
        generator=generator,
        session_manager=session_manager,
        query_rewriter=query_rewriter,
        summarizer=summarizer,
    )


def print_memory_debug(rag: HistoryAwareRAGService, conversation_id: str) -> None:
    memory = rag.session_manager.get_memory(conversation_id)

    print("\n--- Memory Debug ---")
    print(f"Summary: {memory.get_summary() or '[empty]'}")

    recent_messages = memory.get_recent_messages()
    if not recent_messages:
        print("Recent messages: [empty]")
    else:
        print("Recent messages:")
        for message in recent_messages:
            print(f"  {message.role}: {message.content}")
    print("--------------------\n")


def main() -> int:
    load_dotenv()

    rag = build_history_aware_rag()
    conversation_id = str(uuid.uuid4())

    print("Conversational CV RAG terminal")
    print("Type your question and press Enter.")
    print("Type 'exit' or 'quit' to stop.\n")
    print(f"Conversation ID: {conversation_id}\n")

    first_question = " ".join(sys.argv[1:]).strip()
    pending_question = first_question or DEFAULT_QUESTION

    while True:
        question = pending_question.strip()
        pending_question = ""

        if not question:
            question = input("You: ").strip()

        if question.lower() in {"exit", "quit"}:
            break

        if not question:
            continue

        try:
            answer = rag.answer(conversation_id=conversation_id, question=question)
            print(f"\nAssistant: {answer}")
            print_memory_debug(rag, conversation_id)
        except Exception as exc:
            print(f"\nError: {exc}\n")

        next_question = input("You: ").strip()
        if next_question.lower() in {"exit", "quit"}:
            break
        pending_question = next_question

    return 0


if __name__ == "__main__":
    raise SystemExit(main())