from rag_application.llm.prompt_builder import PromptBuilder
from tests.unit.helpers import make_retrieved_chunk


def test_build_prompt_contains_question():
    prompt = PromptBuilder.build_prompt(
        question="Who is Nithusikan?",
        chunks=[
            make_retrieved_chunk(text="Nithusikan is a student."),
        ],
    )

    assert "Who is Nithusikan?" in prompt


def test_build_prompt_contains_context():
    prompt = PromptBuilder.build_prompt(
        question="Who is Nithusikan?",
        chunks=[
            make_retrieved_chunk(text="Nithusikan is a student."),
        ],
    )

    assert "Nithusikan is a student." in prompt
