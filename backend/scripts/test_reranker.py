from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]


def configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def print_chunks(title: str, chunks) -> None:
    print("=" * 80)
    print(title)
    print("=" * 80)

    if not chunks:
        print("No chunks found.")
        print()
        return

    for index, chunk in enumerate(chunks, start=1):
        print(f"{index}. Score={chunk.score:.4f}")
        print(chunk.text[:150])
        print()


def main() -> int:
    configure_output()
    load_dotenv()

    from api_app.wiring.rag_factory import build_history_aware_rag_service

    service = build_history_aware_rag_service()
    query = "Who is Roshan Ragel?"

    # Hybrid retrieval only, so the "before" scores are not already reranked.
    chunks = service.query_service.search(
        query=query,
        top_k=5,
        candidate_k=20,
        use_reranker=False,
    )
    print_chunks("Before Reranking", chunks)

    if not service.query_service.reranker:
        print("No reranker configured.")
        return 1

    reranked = service.query_service.reranker.rerank(
        query=query,
        candidates=chunks,
        top_k=5,
    )
    print_chunks("After Reranking", reranked)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
