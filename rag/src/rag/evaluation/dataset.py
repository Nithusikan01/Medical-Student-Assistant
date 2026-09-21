"""
Reading and writing evaluation sets.

JSON on disk rather than a database table, deliberately. An evaluation
set is an artefact of the repository, not of a deployment: it should be
reviewable in a diff, versioned with the code whose behaviour it pins,
and identical on every machine that runs it. A set that lives only in
one environment's database cannot do any of that.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag.evaluation.schemas import EvaluationDataset, EvaluationExample


class InvalidDatasetError(ValueError):
    """The file is not a usable evaluation set."""


def _example_from(raw: dict[str, Any], index: int) -> EvaluationExample:
    if not isinstance(raw, dict):
        raise InvalidDatasetError(f"Example {index} is not an object.")

    question = str(raw.get("question", "")).strip()

    if not question:
        raise InvalidDatasetError(f"Example {index} has no question.")

    return EvaluationExample(
        id=str(raw.get("id") or f"example-{index + 1}"),
        question=question,
        relevant_chunk_ids=tuple(str(x) for x in raw.get("relevant_chunk_ids", [])),
        relevant_document_ids=tuple(
            str(x) for x in raw.get("relevant_document_ids", [])
        ),
        notes=str(raw.get("notes", "")),
    )


def load_dataset(path: str | Path) -> EvaluationDataset:
    """
    Read an evaluation set, refusing anything ambiguous.

    Malformed examples raise rather than being skipped. A set that
    silently drops half its questions would report a confident average
    over whatever survived, which is worse than not running at all.
    """

    file = Path(path)

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InvalidDatasetError(f"No evaluation set at {file}.") from exc
    except json.JSONDecodeError as exc:
        raise InvalidDatasetError(f"{file} is not valid JSON: {exc}.") from exc

    if not isinstance(raw, dict):
        raise InvalidDatasetError(f"{file} should contain an object.")

    examples = raw.get("examples")

    if not isinstance(examples, list) or not examples:
        raise InvalidDatasetError(f"{file} has no examples.")

    parsed = tuple(
        _example_from(example, index) for index, example in enumerate(examples)
    )

    seen = [example.id for example in parsed]

    if len(set(seen)) != len(seen):
        raise InvalidDatasetError(
            f"{file} has duplicate example ids; scores could not be "
            "attributed to a question."
        )

    return EvaluationDataset(
        name=str(raw.get("name") or file.stem),
        description=str(raw.get("description", "")),
        examples=parsed,
        created_at=datetime.now(UTC),
    )


def save_dataset(dataset: EvaluationDataset, path: str | Path) -> None:
    """Write a set back out, in the format load_dataset reads."""

    payload = {
        "name": dataset.name,
        "description": dataset.description,
        "examples": [
            {
                "id": example.id,
                "question": example.question,
                "relevant_chunk_ids": list(example.relevant_chunk_ids),
                "relevant_document_ids": list(example.relevant_document_ids),
                "notes": example.notes,
            }
            for example in dataset.examples
        ],
    }

    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
