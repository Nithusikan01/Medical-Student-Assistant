from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class EvaluationSample:
    """
    One question-answer pair from evaluation dataset.
    """

    id: int
    question: str
    expected_answer: str

    category: str
    difficulty: str

    expected_keywords: List[str] = field(default_factory=list)

    source_page_numbers: List[int] = field(default_factory=list)
    source_section: Optional[str] = None
    relevant_chunk_hint: Optional[str] = None

    requires_multi_hop: bool = False
    answer_type: str = "text"

    # If your dataset includes ground-truth chunks (recommended)
    expected_chunk_ids: List[str] = field(default_factory=list)


@dataclass
class RetrievalTestSample:
    """
    Retrieval-only evaluation sample.
    """

    id: int
    question: str
    expected_chunk_ids: List[str] = field(default_factory=list)


@dataclass
class RetrievedChunkResult:
    id: str
    score: float
    text: str
    metadata: Dict[str, Any]


@dataclass
class RetrievalEvaluationResult:
    question_id: int
    question: str

    retrieved_chunk_ids: List[str]
    expected_chunk_ids: List[str]

    recall_at_k: float
    precision_at_k: float
    hit_rate: float
    mrr: float


@dataclass
class GenerationEvaluationResult:
    question_id: int
    question: str

    expected_answer: str
    generated_answer: str

    exact_match: float
    f1: float
    rouge_l: float
    bleu: float
    semantic_similarity: float

    llm_judge_score: Optional[float] = None
    llm_judge_reason: Optional[str] = None


@dataclass
class RAGEvaluationResult:
    question_id: int
    question: str

    retrieval: RetrievalEvaluationResult
    generation: GenerationEvaluationResult

@dataclass
class EvaluationReport:
    total_questions: int

    avg_recall_at_k: float
    avg_precision_at_k: float
    avg_mrr: float
    avg_hit_rate: float

    avg_exact_match: float
    avg_semantic_similarity: float
    avg_llm_score: float

    failed_questions: List[int] = field(default_factory=list)

    raw_results: List[RAGEvaluationResult] = field(default_factory=list)


@dataclass(slots=True)
class LLMJudgeResult:
    faithfulness: float
    correctness: float
    completeness: float
    groundedness: float
    reason: str
