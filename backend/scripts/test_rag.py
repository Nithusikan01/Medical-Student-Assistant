from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]

if TYPE_CHECKING:
    from rag_application.retrieval.schemas import RetrievedChunk


DEFAULT_QUESTION = "Who is Nithusikan?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a one-shot history-aware RAG query."
    )
    parser.add_argument(
        "question",
        nargs="*",
        help=f"Question to ask. Defaults to: {DEFAULT_QUESTION}",
    )
    parser.add_argument(
        "--conversation-id",
        default="script-test",
        help="Conversation id used for memory-aware query rewriting.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of source chunks to retrieve for the answer.",
    )
    parser.add_argument(
        "--hide-sources",
        action="store_true",
        help="Only print the generated answer.",
    )
    return parser.parse_args()


def print_sources(chunks: list[RetrievedChunk]) -> None:
    if not chunks:
        print("\nSOURCES: [none]")
        return

    print("\nSOURCES:")
    for index, chunk in enumerate(chunks, start=1):
        source = chunk.metadata.filename or chunk.metadata.source_path
        method = chunk.retrieval_method or "unknown"
        preview = " ".join(chunk.text.split())
        if len(preview) > 260:
            preview = f"{preview[:257]}..."

        print(
            f"{index}. {chunk.id} | score={chunk.score:.4f} "
            f"| method={method} | source={source}"
        )
        print(f"   {preview}")


def main() -> int:
    args = parse_args()
    load_dotenv()

    from api_app.wiring.rag_factory import build_history_aware_rag_service

    question = " ".join(args.question).strip() or DEFAULT_QUESTION
    rag = build_history_aware_rag_service()

    answer, chunks = rag.answer_with_sources(
        conversation_id=args.conversation_id,
        question=question,
        top_k=args.top_k,
    )

    print("\nQUESTION:")
    print(question)
    print("\nANSWER:")
    print(answer)

    if not args.hide_sources:
        print_sources(chunks)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
