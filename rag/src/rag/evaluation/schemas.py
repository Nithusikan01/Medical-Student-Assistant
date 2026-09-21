"""
The shape of an evaluation set and of a result.

An evaluation example is a question plus the chunk ids that genuinely
answer it. That second half is the expensive part: it has to be written
by someone who knows the corpus, and it cannot be mined from production
traffic - retrieval logs record what was returned, never what should
have been.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """
    One question with known-correct answers.

    `relevant_chunk_ids` are ids from document_chunks, which are also the
    Pinecone vector ids - so a label survives re-ingestion only if the
    document is unchanged. Re-chunking invalidates a labelled set, and
    that is worth knowing before spending a day writing one.

    `relevant_document_ids` is the coarser fallback: when a question is
    answered by a document rather than a passage, labelling at document
    level is far cheaper and the runner scores it separately rather than
    pretending the two are the same measurement.
    """

    id: str
    question: str

    relevant_chunk_ids: tuple[str, ...] = ()
    relevant_document_ids: tuple[str, ...] = ()

    # Free text for whoever maintains the set: why this question is here,
    # what makes it hard. Never used in scoring.
    notes: str = ""

    @property
    def labelled(self) -> bool:
        return bool(self.relevant_chunk_ids or self.relevant_document_ids)


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """A named set of labelled questions."""

    name: str
    examples: tuple[EvaluationExample, ...]

    description: str = ""
    created_at: datetime | None = None

    @property
    def labelled_examples(self) -> tuple[EvaluationExample, ...]:
        return tuple(example for example in self.examples if example.labelled)

    @property
    def unlabelled_count(self) -> int:
        return len(self.examples) - len(self.labelled_examples)


@dataclass(frozen=True, slots=True)
class ExampleResult:
    """What retrieval did on one example."""

    example_id: str
    question: str

    retrieved_chunk_ids: tuple[str, ...]
    retrieved_document_ids: tuple[str, ...]

    # Per-example scores, so a bad question can be found rather than just
    # lowering an average nobody can explain.
    scores: dict[str, float | None] = field(default_factory=dict)

    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """
    The result of running a dataset against a retriever.

    `config` records what was being evaluated - top_k, which retriever,
    which models. Without it a report is a number with no claim attached,
    and two reports cannot be meaningfully compared.
    """

    dataset: str
    ran_at: datetime

    examples: tuple[ExampleResult, ...]
    summary: dict[str, float | None]

    config: dict[str, Any] = field(default_factory=dict)

    skipped_unlabelled: int = 0
    failed: int = 0

    @property
    def evaluated(self) -> int:
        return len(self.examples) - self.failed
