from rag_application.llm.prompt_builder import PromptBuilder
from rag_application.retrieval.schemas import RetrievedChunk


def test_build_prompt_contains_question():

    chunks = [
        RetrievedChunk(
            id="1",
            score=0.9,
            text="Nithusikan is a student."
        )
    ]

    prompt = PromptBuilder.build_prompt(
        question="Who is Nithusikan?",
        chunks=chunks
    )

    assert "Who is Nithusikan?" in prompt


def test_build_prompt_contains_context():

    chunks = [
        RetrievedChunk(
            id="1",
            score=0.9,
            text="Nithusikan is a student."
        )
    ]

    prompt = PromptBuilder.build_prompt(
        question="Who is Nithusikan?",
        chunks=chunks
    )

    assert "Nithusikan is a student." in prompt