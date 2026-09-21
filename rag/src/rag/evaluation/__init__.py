"""
Offline retrieval evaluation.

Everything in this package needs **ground truth** - questions paired with
the passages that genuinely answer them. That is what separates it from
every other measurement in this project, and why none of it appears in
the operational dashboard.

The distinction, stated once:

  - `backend/observability/` measures **what happened**: how long, how
    much, how often it failed. Derivable from production traffic, and
    reported live.
  - This package measures **whether it was any good**: Recall@K,
    Precision@K, MRR, nDCG. Not derivable from production traffic at any
    volume, and reported only when someone runs it against a labelled
    set.

Conflating them is the failure mode the whole upgrade was written to
avoid. A green dashboard means the system behaved; it has never meant
the answers were right.

Run it with `backend/scripts/evaluate_retrieval.py`.
"""

from rag.evaluation.comparison import Comparison, MetricDelta, compare
from rag.evaluation.dataset import InvalidDatasetError, load_dataset, save_dataset
from rag.evaluation.metrics import (
    average_precision,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from rag.evaluation.runner import DEFAULT_K_VALUES, evaluate, score_example, summarize
from rag.evaluation.schemas import (
    EvaluationDataset,
    EvaluationExample,
    EvaluationReport,
    ExampleResult,
)

__all__ = [
    "DEFAULT_K_VALUES",
    "Comparison",
    "EvaluationDataset",
    "EvaluationExample",
    "EvaluationReport",
    "ExampleResult",
    "InvalidDatasetError",
    "MetricDelta",
    "average_precision",
    "compare",
    "evaluate",
    "load_dataset",
    "mean",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "save_dataset",
    "score_example",
    "summarize",
]
