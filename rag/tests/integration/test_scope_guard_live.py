"""
The scope guard against the real model.

The unit tests fix how a verdict is parsed and acted on; only the model
decides the verdict. These tables are what the prompt is tuned against:
run them after changing the prompt, the subject, or the model.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / "backend" / ".env")

if os.getenv("RUN_REAL_RAG_TESTS") != "1":
    pytest.skip(
        "Set RUN_REAL_RAG_TESTS=1 to run live Gemini integration tests.",
        allow_module_level=True,
    )

from rag.config.settings import settings_from_mapping
from rag.conversation.scope_guard import ScopeGuard
from rag.llm.generator import GeminiGenerator

# A false refusal here costs a student a real answer: these must pass.
IN_SCOPE = [
    "What is the mechanism of action of metformin?",
    "Explain the Frank-Starling law",
    "Difference between type 1 and type 2 respiratory failure",
    "What are the side effects of ACE inhibitors?",
    "How do I calculate the anion gap?",
    "Summarise the brachial plexus",
    "What is a confidence interval?",
    "How should I revise for my pharmacology exam?",
    "Which enzymes are involved in glycolysis?",
    "What does the lecture say about sepsis management?",
    "Ethics of consent in a 15 year old",
    "What is the paediatric dose of paracetamol?",
    # Calculations and study aids that are part of the subject, not tricks.
    "Calculate gentamicin 5 mg/kg for a 70 kg patient",
    "What is the BMI of a 70 kg person who is 1.75 m tall?",
    "Give me a mnemonic for the cranial nerves",
    "Write three MCQs on heart failure for my exam",
]

OUT_OF_SCOPE = [
    "Write a Python function to reverse a linked list",
    "Who won the Premier League last season?",
    "Recommend a good laptop for under 1000 dollars",
    "Plan a three day trip to Paris",
    "Write a poem about the sea",
    "What is the capital of Australia?",
    "Who should I vote for in the election?",
    "What is 5 multiply by 12",
    # Medical words around a question that is not about studying medicine.
    "What is 2 eyes plus 2 eyes?",
    "If a patient has 2 kidneys and gets 3 more, how many kidneys?",
    "How many legs do 3 surgeons have?",
    "Tell me a joke about doctors",
    "Write a love poem about the heart",
]


@pytest.fixture(scope="module")
def guard() -> ScopeGuard:
    settings = settings_from_mapping(os.environ)

    return ScopeGuard(
        GeminiGenerator(settings.generation_config()),
        settings.scope_config(),
    )


@pytest.mark.parametrize("question", IN_SCOPE)
def test_study_questions_are_answered(guard, question):
    assert guard.is_in_scope(question)


@pytest.mark.parametrize("question", OUT_OF_SCOPE)
def test_unrelated_questions_are_declined(guard, question):
    assert not guard.is_in_scope(question)
