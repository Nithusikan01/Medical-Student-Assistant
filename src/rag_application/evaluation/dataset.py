"""
Responsibility: 
- Load an evaluation dataset from JSON and 
  convert it into strongly typed 
  EvaluationSample objects.
"""
import json
from pathlib import Path
from typing import List

from rag_application.evaluation.schemas import (
    EvaluationSample,
    RetrievalTestSample,
)


class DatasetLoader:
    """
    Loads an evaluation dataset from a JSON file.

    Expected JSON format:

    {
        "document_name": "...",
        "questions": [
            {
                ...
            }
        ]
    }
    """

    def __init__(self, dataset_path: str | Path):
        self.dataset_path = Path(dataset_path)

    def load(self) -> List[EvaluationSample]:

        if not self.dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.dataset_path}"
            )

        with open(
            self.dataset_path,
            "r",
            encoding="utf-8"
        ) as f:
            dataset = json.load(f)

        if "questions" not in dataset:
            raise ValueError(
                "Invalid dataset format. Missing 'questions' field."
            )

        samples = []

        for item in dataset["questions"]:

            sample = EvaluationSample(

                id=item["id"],

                question=item["question"],

                expected_answer=item["expected_answer"],

                category=item["category"],

                difficulty=item["difficulty"],

                expected_keywords=item.get(
                    "expected_keywords",
                    []
                ),

                source_page_numbers=item.get(
                    "source_page_numbers",
                    []
                ),

                source_section=item.get(
                    "source_section"
                ),

                relevant_chunk_hint=item.get(
                    "relevant_chunk_hint"
                ),

                requires_multi_hop=item.get(
                    "requires_multi_hop",
                    False
                ),

                answer_type=item.get(
                    "answer_type",
                    "text"
                ),

                expected_chunk_ids=item.get(
                    "expected_chunk_ids",
                    []
                )
            )

            samples.append(sample)

        return samples


class RetrievalDatasetLoader:
    """
    Loads a retrieval-only dataset from a JSON file.

    Expected JSON format:

    [
        {
            "question_id": 1,
            "question": "...",
            "expected_chunk_ids": ["chunk_1"]
        }
    ]
    """

    def __init__(self, dataset_path: str | Path):
        self.dataset_path = Path(dataset_path)

    def load(self) -> List[RetrievalTestSample]:

        if not self.dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {self.dataset_path}"
            )

        with open(
            self.dataset_path,
            "r",
            encoding="utf-8"
        ) as f:
            dataset = json.load(f)

        if not isinstance(dataset, list):
            raise ValueError(
                "Invalid retrieval dataset format. Expected a JSON array."
            )

        samples = []

        for item in dataset:
            samples.append(
                RetrievalTestSample(
                    id=item["question_id"],
                    question=item["question"],
                    expected_chunk_ids=item.get(
                        "expected_chunk_ids",
                        []
                    ),
                )
            )

        return samples
