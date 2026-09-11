import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

if os.getenv("RUN_REAL_RAG_TESTS") != "1":
    pytest.skip(
        "Set RUN_REAL_RAG_TESTS=1 to run live Pinecone/Gemini integration tests.",
        allow_module_level=True,
    )

pytest.importorskip("rank_bm25")
pytest.importorskip("sentence_transformers")

from backend.wiring.rag_factory import build_history_aware_rag_service


def test_full_rag_pipeline():
    rag = build_history_aware_rag_service()

    answer = rag.answer(
        conversation_id="integration-test",
        question="Who is Nithusikan?",
    )

    assert answer is not None
    assert isinstance(answer, str)
    assert len(answer) > 0
