from rag.config.component_configs import PromptConfig
from rag.llm.prompt_builder import PromptBuilder
from tests.unit.helpers import make_retrieved_chunk


def test_build_prompt_contains_question():
    prompt = PromptBuilder().build_prompt(
        question="Who is Nithusikan?",
        chunks=[
            make_retrieved_chunk(text="Nithusikan is a student."),
        ],
    )

    assert "Who is Nithusikan?" in prompt


def test_build_prompt_contains_context():
    prompt = PromptBuilder().build_prompt(
        question="Who is Nithusikan?",
        chunks=[
            make_retrieved_chunk(text="Nithusikan is a student."),
        ],
    )

    assert "Nithusikan is a student." in prompt


def test_build_prompt_uses_the_configured_wording():
    builder = PromptBuilder(
        PromptConfig(
            corpus_description="the cardiology lecture notes",
            no_answer_text="Not in your notes.",
        )
    )

    prompt = builder.build_prompt(question="q", chunks=[make_retrieved_chunk()])

    assert "the cardiology lecture notes" in prompt
    assert "Not in your notes." in prompt


def test_build_prompt_is_not_indented_by_multiline_context():
    """
    Substituting multi-line text before dedent left every line at column
    zero, so dedent found no common indent and the rules reached the model
    indented by twelve spaces.
    """

    prompt = PromptBuilder().build_prompt(
        question="q",
        chunks=[make_retrieved_chunk(text="line one\nline two")],
        recent_messages=None,
    )

    assert "\n- Answer ONLY using the supplied context." in prompt
    assert all(not line.startswith("    ") for line in prompt.splitlines())


def test_build_prompt_survives_braces_in_the_context():
    prompt = PromptBuilder().build_prompt(
        question="What is {x}?",
        chunks=[make_retrieved_chunk(text="A set {a, b} and {}")],
    )

    assert "A set {a, b} and {}" in prompt
    assert "What is {x}?" in prompt


def test_no_context_answer_comes_from_config():
    builder = PromptBuilder(PromptConfig(no_context_answer="Nothing found."))

    assert builder.no_context_answer == "Nothing found."


def test_page_labels_cover_single_spanning_and_legacy_chunks():
    from rag.llm.prompt_builder import page_label

    assert page_label(4, 4) == "Page: 4"
    assert page_label(4, 5) == "Pages: 4-5"
    assert page_label(4, None) == "Page: 4"
    assert page_label(None, None) is None
