import json
import re
from typing import Optional

from rag_application.evaluation.schemas import LLMJudgeResult
from rag_application.llm.generator import GeminiGenerator


class LLMJudge:
    """
    Uses an LLM to evaluate the quality of generated RAG answers.

    Evaluates:
    - Faithfulness
    - Correctness
    - Completeness
    - Groundedness
    """

    def __init__(
        self,
        generator: GeminiGenerator,
    ):
        self.generator = generator

    def judge(
        self,
        question: str,
        expected_answer: str,
        generated_answer: str,
        retrieved_context: str,
    ) -> LLMJudgeResult:

        prompt = f"""
You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.

Your task is to evaluate the generated answer using ONLY the retrieved context.

Question:
{question}

Expected Answer:
{expected_answer}

Retrieved Context:
{retrieved_context}

Generated Answer:
{generated_answer}

Evaluate the answer according to these criteria:

1. Faithfulness
- Is the generated answer fully supported by the retrieved context?
- Score: 1 (poor) to 5 (excellent)

2. Correctness
- Does the answer correctly answer the question?
- Score: 1 to 5

3. Completeness
- Does the answer include all important information?
- Score: 1 to 5

4. Groundedness
- Is every claim grounded in the retrieved context?
- Score: 1 to 5

Also provide one short explanation.

Return ONLY valid JSON.

Example:

{{
    "faithfulness": 5,
    "correctness": 4,
    "completeness": 5,
    "groundedness": 5,
    "reason": "The answer is accurate and fully supported by the retrieved context."
}}
"""

        response = self.generator.generate(prompt)

        data = self._parse_json(response.text)

        return LLMJudgeResult(
            faithfulness=float(data["faithfulness"]),
            correctness=float(data["correctness"]),
            completeness=float(data["completeness"]),
            groundedness=float(data["groundedness"]),
            reason=data["reason"],
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        """
        Extract JSON from the LLM response.
        Handles responses wrapped in Markdown code fences.
        """

        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text)
            text = re.sub(r"```$", "", text)
            text = text.strip()

        return json.loads(text)