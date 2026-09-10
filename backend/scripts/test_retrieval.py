from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]

if TYPE_CHECKING:
    from rag_application.ingestion.schemas import DocumentChunk
    from rag_application.retrieval.query_service import QueryService
    from rag_application.retrieval.schemas import RetrievedChunk


DEFAULT_QUERY = "Who is Nithusikan?"
DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[1] / "storage" / "bm25_corpus.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the current retrieval workflow: dense + BM25 hybrid search with optional reranking."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help=f"Query to retrieve for. Defaults to: {DEFAULT_QUERY}",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of final chunks to print.",
    )
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=20,
        help="Number of candidates to retrieve before reranking.",
    )
    parser.add_argument(
        "--corpus-path",
        default=str(DEFAULT_CORPUS_PATH),
        help="Path to storage/bm25_corpus.json written by ingestion.",
    )
    parser.add_argument(
        "--no-reranker",
        action="store_true",
        help="Skip CrossEncoder reranking and print raw hybrid results.",
    )
    return parser.parse_args()


def load_bm25_documents(corpus_path: Path) -> list[DocumentChunk]:
    from api_app.wiring.rag_factory import load_bm25_corpus

    if not corpus_path.exists():
        print(f"BM25 corpus not found at {corpus_path}. BM25 retrieval will be empty.")
        return []

    return load_bm25_corpus(corpus_path)


def build_query_service(corpus_path: Path, use_reranker: bool) -> QueryService:
    from rag_application.config.settings import load_settings
    from rag_application.indexes.bm25_index import BM25Index
    from rag_application.ingestion.embedder import Embedder
    from rag_application.retrieval.bm25_retriever import BM25Retriever
    from rag_application.retrieval.dense_retriever import DenseRetriever
    from rag_application.retrieval.hybrid_retriever import HybridRetriever
    from rag_application.retrieval.query_service import QueryService
    from rag_application.retrieval.reranker import Reranker
    from rag_application.vectorstore.pinecone_store import PineconeVectorStore

    settings = load_settings()

    embedder = Embedder(settings.embedding_config())
    dimension = len(embedder.model.encode("dimension_check"))

    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=dimension,
    )

    dense_retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )

    bm25_index = BM25Index(load_bm25_documents(corpus_path))
    bm25_retriever = BM25Retriever(bm25_index=bm25_index)

    hybrid_retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
    )

    reranker = None if not use_reranker else Reranker()

    return QueryService(
        retriever=hybrid_retriever,
        reranker=reranker,
    )


def print_results(results: list[RetrievedChunk]) -> None:
    if not results:
        print("No retrieval results found.")
        return

    print(f"Retrieved {len(results)} chunks:\n")
    for index, result in enumerate(results, start=1):
        source = result.metadata.filename or result.metadata.source_path
        preview = " ".join(result.text.split())
        if len(preview) > 320:
            preview = f"{preview[:317]}..."

        print(f"{index}. Chunk ID: {result.id}")
        print(f"   Score: {result.score:.4f}")
        print(f"   Method: {result.retrieval_method or 'unknown'}")
        print(f"   Source: {source}")
        print(f"   Text: {preview}\n")


def main() -> int:
    args = parse_args()
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    query = " ".join(args.query).strip() or DEFAULT_QUERY
    corpus_path = Path(args.corpus_path).expanduser().resolve()

    print("Starting retrieval workflow test...")
    print(f"Query: {query}")
    print(f"BM25 corpus: {corpus_path}")
    print(f"Reranker: {'disabled' if args.no_reranker else 'enabled'}\n")

    query_service = build_query_service(
        corpus_path=corpus_path,
        use_reranker=not args.no_reranker,
    )

    results = query_service.search(
        query=query,
        top_k=args.top_k,
        candidate_k=args.candidate_k,
        use_reranker=not args.no_reranker,
    )

    print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
