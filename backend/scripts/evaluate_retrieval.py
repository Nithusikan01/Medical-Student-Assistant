"""
Run an evaluation set against the live retrieval stack.

    cd backend
    python scripts/evaluate_retrieval.py data/evaluation/example.json
    python scripts/evaluate_retrieval.py data/evaluation/example.json --save runs/before.json
    python scripts/evaluate_retrieval.py --compare runs/before.json runs/after.json

Named `evaluate_` rather than `test_` so pytest cannot collect it, the
same convention the smoke scripts follow.

This talks to the real Pinecone index and the real database, so it costs
what a batch of queries costs. It is offline in the sense that matters -
it is not on the request path and nothing it produces reaches the
operational dashboard - not in the sense of being free.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from rag.evaluation import (
    EvaluationReport,
    compare,
    evaluate,
    load_dataset,
)
from rag.evaluation.comparison import DEFAULT_SIGNIFICANCE


def build_retriever():
    """
    The same retriever the query path uses, built the same way.

    Evaluating anything else would measure a system nobody is running.
    """

    from backend.wiring.rag_factory import build_hybrid_retriever

    return build_hybrid_retriever()


def render(report: EvaluationReport) -> None:
    print(f"\n{report.dataset} - {report.evaluated} examples")
    print(f"  config: {report.config}")

    if report.skipped_unlabelled:
        print(
            f"  skipped: {report.skipped_unlabelled} unlabelled "
            "(not scored as misses)"
        )

    if report.failed:
        print(f"  failed:  {report.failed}")

    print()

    for name, value in sorted(report.summary.items()):
        # "not measured" and 0.0 are different findings and must not print
        # the same way.
        shown = "not measured" if value is None else f"{value:.3f}"
        print(f"  {name:<24} {shown}")

    print()


def render_comparison(baseline: EvaluationReport, candidate: EvaluationReport) -> None:
    result = compare(baseline, candidate)

    if not result.comparable:
        print(f"\n{result.note}\n")
        return

    print(
        f"\n{result.dataset}: {baseline.ran_at:%Y-%m-%d} -> {candidate.ran_at:%Y-%m-%d}"
    )

    if result.config_changes:
        print("\n  configuration changed:")

        for key, (before, after) in sorted(result.config_changes.items()):
            print(f"    {key}: {before} -> {after}")
    else:
        print("\n  configuration unchanged")

    print()

    for metric in sorted(result.metrics, key=lambda item: item.metric):
        delta = metric.delta

        if delta is None:
            print(f"  {metric.metric:<24} not comparable")
            continue

        arrow = metric.direction(DEFAULT_SIGNIFICANCE)
        print(f"  {metric.metric:<24} {delta:+.3f}  ({arrow})")

    if result.looks_like_drift:
        print(
            "\n  Metrics moved while the configuration did not. The corpus "
            "changed underneath: documents added, removed, or re-chunked."
        )

    print()


def load_report(path: str | Path) -> EvaluationReport:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    from datetime import datetime

    from rag.evaluation.schemas import ExampleResult

    return EvaluationReport(
        dataset=raw["dataset"],
        ran_at=datetime.fromisoformat(raw["ran_at"]),
        examples=tuple(ExampleResult(**example) for example in raw["examples"]),
        summary=raw["summary"],
        config=raw.get("config", {}),
        skipped_unlabelled=raw.get("skipped_unlabelled", 0),
        failed=raw.get("failed", 0),
    )


def save_report(report: EvaluationReport, path: str | Path) -> None:
    payload = asdict(report)
    payload["ran_at"] = report.ran_at.isoformat()

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=list) + "\n",
        encoding="utf-8",
    )

    print(f"Saved to {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("dataset", nargs="?", help="Path to an evaluation set.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--save", help="Write the report here, for later comparison.")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "CANDIDATE"),
        help="Compare two saved reports instead of running anything.",
    )

    arguments = parser.parse_args()

    if arguments.compare:
        render_comparison(*(load_report(path) for path in arguments.compare))
        return 0

    if not arguments.dataset:
        parser.error("a dataset is required unless --compare is given")

    dataset = load_dataset(arguments.dataset)

    if not dataset.labelled_examples:
        print(
            f"{dataset.name} has no labelled examples. Nothing can be "
            "measured without known-correct answers - that is the whole "
            "point of this script, and the reason these numbers do not "
            "appear on the dashboard."
        )
        return 1

    report = evaluate(
        build_retriever(),
        dataset,
        top_k=arguments.top_k,
        config={"retriever": "hybrid"},
    )

    render(report)

    if arguments.save:
        save_report(report, arguments.save)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
