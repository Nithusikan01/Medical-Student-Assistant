from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "backend" / "src"), str(_ROOT / "rag" / "src")]


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "evaluation" / "cv.json"
)
DEFAULT_RETRIEVAL_DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "evaluation"
    / "retrieval_test_dataset.json"
)
DEFAULT_OUTPUT_JSON = (
    Path(__file__).resolve().parents[1] / "logs" / "rag_evaluation_report.json"
)
DEFAULT_OUTPUT_MD = (
    Path(__file__).resolve().parents[1] / "logs" / "rag_evaluation_report.md"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the RAG pipeline against a JSON question set."
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to the evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--retrieval-dataset",
        default=str(DEFAULT_RETRIEVAL_DATASET_PATH),
        help="Path to the retrieval-only evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of final chunks to retrieve per question.",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="Where to write the full evaluation report as JSON.",
    )
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
        help="Where to write a short Markdown summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()

    from rag_application.evaluation.dataset import DatasetLoader
    from rag_application.evaluation.exporter import EvaluationExporter
    from rag_application.evaluation.generation_evaluator import GenerationEvaluator
    from rag_application.evaluation.report import EvaluationReport
    from rag_application.evaluation.retrieval_evaluator import RetrievalEvaluator
    from rag_application.evaluation.dataset import RetrievalDatasetLoader
    from rag_application.retrieval.query_service import QueryService
    from rag_application.utils.logger import setup_logging
    from api_app.wiring.rag_factory import build_history_aware_rag_service

    setup_logging()

    dataset_path = Path(args.dataset).expanduser().resolve()
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        return 1

    samples = DatasetLoader(dataset_path).load()
    if not samples:
        print(f"No evaluation samples found in {dataset_path}")
        return 1

    retrieval_dataset_path = Path(args.retrieval_dataset).expanduser().resolve()
    retrieval_samples = []
    if retrieval_dataset_path.exists():
        retrieval_samples = RetrievalDatasetLoader(retrieval_dataset_path).load()

    if not retrieval_samples:
        retrieval_samples = [
            sample for sample in samples if sample.expected_chunk_ids
        ]

    rag_service = build_history_aware_rag_service()
    query_service: QueryService = rag_service.query_service

    retrieval_evaluator = RetrievalEvaluator(query_service=query_service)
    generation_evaluator = GenerationEvaluator(rag_service=rag_service)

    if retrieval_samples:
        retrieval_results = retrieval_evaluator.evaluate_dataset(
            dataset=retrieval_samples,
            top_k=args.top_k,
        )
    else:
        retrieval_results = []
        print(
            "Retrieval metrics skipped because no retrieval dataset or expected_chunk_ids were provided."
        )

    generation_results = generation_evaluator.evaluate_dataset(dataset=samples)

    report = EvaluationReport(
        retrieval_results=retrieval_results,
        generation_results=generation_results,
    ).build()

    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    EvaluationExporter.export_json(report, output_json)

    output_md = Path(args.output_md).expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    EvaluationExporter.export_markdown(report, output_md)

    summary = {
        "retrieval": report["retrieval_summary"],
        "generation": report["generation_summary"],
    }

    print("Evaluation complete.")
    print(f"Dataset: {dataset_path}")
    print(f"Questions: {len(samples)}")
    print(f"JSON report: {output_json}")
    print(f"Markdown report: {output_md}")
    print("\nGeneration summary:")
    for metric_name, metric_value in summary["generation"].items():
        print(f"- {metric_name}: {metric_value:.4f}")

    if summary["retrieval"]:
        print("\nRetrieval summary:")
        for metric_name, metric_value in summary["retrieval"].items():
            print(f"- {metric_name}: {metric_value:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())