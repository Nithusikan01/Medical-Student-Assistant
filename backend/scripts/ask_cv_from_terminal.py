from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]

if TYPE_CHECKING:
    from rag.retrieval.schemas import RetrievedChunk
    from rag.services.history_aware_rag_service import HistoryAwareRAGService


DEFAULT_QUESTION = "Who is the person in the CV?"
EXIT_COMMANDS = {"exit", "quit"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a history-aware RAG chat session in the terminal."
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Optional first question. If omitted, a default CV question is used.",
    )
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="Reuse a conversation id for follow-up context. Defaults to a new UUID.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of source chunks to use for each answer.",
    )
    parser.add_argument(
        "--hide-memory",
        action="store_true",
        help="Do not print memory debug information after each answer.",
    )
    parser.add_argument(
        "--hide-sources",
        action="store_true",
        help="Do not print retrieved source chunks after each answer.",
    )
    return parser.parse_args()


def build_history_aware_rag() -> HistoryAwareRAGService:
    from backend.wiring.rag_factory import build_history_aware_rag_service

    return build_history_aware_rag_service()


def print_sources(chunks: list[RetrievedChunk]) -> None:
    if not chunks:
        print("\nSources: [none]\n")
        return

    print("\nSources:")
    for index, chunk in enumerate(chunks, start=1):
        source = chunk.metadata.filename or chunk.metadata.source_path
        method = chunk.retrieval_method or "unknown"
        preview = " ".join(chunk.text.split())
        if len(preview) > 220:
            preview = f"{preview[:217]}..."

        print(
            f"  {index}. {chunk.id} | score={chunk.score:.4f} "
            f"| method={method} | source={source}"
        )
        print(f"     {preview}")
    print()


def print_memory_debug(rag: HistoryAwareRAGService, conversation_id: str) -> None:
    memory = rag.session_manager.get_memory(conversation_id)

    print("--- Memory Debug ---")
    print(f"Summary: {memory.get_summary() or '[empty]'}")

    recent_messages = memory.get_recent_messages()
    if not recent_messages:
        print("Recent messages: [empty]")
    else:
        print("Recent messages:")
        for message in recent_messages:
            print(f"  {message.role}: {message.content}")
    print("--------------------\n")


def read_next_question() -> str:
    try:
        return input("You: ").strip()
    except EOFError:
        return "exit"


def main() -> int:
    args = parse_args()
    load_dotenv()

    rag = build_history_aware_rag()
    conversation_id = args.conversation_id or str(uuid.uuid4())

    print("Conversational RAG terminal")
    print("Type your question and press Enter.")
    print("Type 'exit' or 'quit' to stop.\n")
    print(f"Conversation ID: {conversation_id}\n")

    first_question = " ".join(args.question).strip()
    pending_question = first_question or DEFAULT_QUESTION

    while True:
        question = pending_question.strip()
        pending_question = ""

        if not question:
            question = read_next_question()

        if question.lower() in EXIT_COMMANDS:
            break

        if not question:
            continue

        try:
            answer, chunks = rag.answer_with_sources(
                conversation_id=conversation_id,
                question=question,
                top_k=args.top_k,
            )
            print(f"\nAssistant: {answer}\n")

            if not args.hide_sources:
                print_sources(chunks)

            if not args.hide_memory:
                print_memory_debug(rag, conversation_id)

        except Exception as exc:
            print(f"\nError: {exc}\n")

        pending_question = read_next_question()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
