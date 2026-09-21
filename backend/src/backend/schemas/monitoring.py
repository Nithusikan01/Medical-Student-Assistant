"""
Response models for the monitoring API.

Two conventions run through all of these, both inherited from the metric
layer and both worth stating because they change how a client must render
the result:

- **Null is not zero.** A percentile that is absent means nothing happened,
  not that everything took no time. A cost of null means the model is not
  priced, not that it was free. Rendering either as 0 states something the
  data does not support.
- **Operational, not quality.** Nothing here claims an answer was good.
  Recall@K, faithfulness and the rest need ground truth (section 54), and
  no field in this module should imply otherwise.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class WindowInfo(BaseModel):
    """Which window the numbers cover, echoed so a chart can label itself."""

    start: datetime
    end: datetime
    range: str | None = None
    bucket_seconds: int


class LatencyInfo(BaseModel):
    count: int
    # Absent when nothing ran. Not zero.
    p50_ms: float | None = None
    p75_ms: float | None = None
    p90_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None


class RequestInfo(BaseModel):
    total: int

    succeeded: int
    client_errors: int
    failed: int

    success_rate: float
    client_error_rate: float
    failure_rate: float

    requests_per_minute: float

    latency: LatencyInfo


class StageLatencyInfo(BaseModel):
    stage: str
    count: int
    errors: int
    error_rate: float
    latency: LatencyInfo


class SeriesPointInfo(BaseModel):
    start: datetime
    total: int
    succeeded: int
    client_errors: int
    failed: int
    p95_ms: float | None = None


class InFlightInfo(BaseModel):
    """
    Requests in progress right now.

    Per process and lost on restart: a trace row is only written when a
    request finishes, so this cannot come from the database. With more than
    one task running, this is that task's share and not the service total -
    which the client must say rather than imply.
    """

    current: int
    peak: int
    per_process: bool = True


class OverviewResponse(BaseModel):
    window: WindowInfo
    requests: RequestInfo
    slowest_stages: list[StageLatencyInfo] = Field(default_factory=list)
    in_flight: InFlightInfo
    total_tokens: int
    estimated_cost_usd: Decimal | None = None
    pricing_configured: bool = False
    error_count: int


class PerformanceResponse(BaseModel):
    window: WindowInfo
    requests: RequestInfo
    stages: list[StageLatencyInfo] = Field(default_factory=list)
    series: list[SeriesPointInfo] = Field(default_factory=list)
    routes: list["RouteCountInfo"] = Field(default_factory=list)


class RouteCountInfo(BaseModel):
    route: str
    count: int


# ----------------------------------------------------------------------
# Tokens and cost
# ----------------------------------------------------------------------


class ModelSpendInfo(BaseModel):
    model_id: str
    provider: str

    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # Null means no pricing row covered this model. Render "not priced".
    estimated_cost_usd: Decimal | None = None
    priced_calls: int = 0


class StageSpendInfo(BaseModel):
    stage: str
    calls: int
    total_tokens: int
    estimated_cost_usd: Decimal | None = None


class TokensResponse(BaseModel):
    window: WindowInfo

    total_tokens: int
    prompt_tokens: int
    completion_tokens: int

    estimated_cost_usd: Decimal | None = None
    pricing_configured: bool = False

    by_model: list[ModelSpendInfo] = Field(default_factory=list)

    # The breakdown that answers *why* consumption moved. Three of these
    # stages were not counted at all before phase 6.
    by_stage: list[StageSpendInfo] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------


class DistributionInfo(BaseModel):
    count: int = 0
    mean: float | None = None
    p50: float | None = None
    p95: float | None = None
    minimum: float | None = None
    maximum: float | None = None


class RetrieverInfo(BaseModel):
    stage: str
    calls: int

    # A retriever that has quietly stopped matching shows up here and
    # nowhere else - there is no error to catch.
    empty_calls: int
    empty_rate: float

    result_count: DistributionInfo
    top_score: DistributionInfo
    average_score: DistributionInfo


class FusionInfo(BaseModel):
    calls: int

    # Null rather than 0 when nothing was retrieved: a share of nothing is
    # undefined.
    dense_only_share: float | None = None
    bm25_only_share: float | None = None
    overlap_share: float | None = None

    single_retriever_calls: int
    single_retriever_rate: float

    overlap_count: DistributionInfo
    unique_count: DistributionInfo


class RerankingInfo(BaseModel):
    calls: int

    reranker_usage: dict[str, int] = Field(default_factory=dict)

    degraded_calls: int
    degraded_rate: float

    # Whether reranking changed the selection. Deliberately not framed as an
    # improvement - only an evaluation set could say that.
    changed_calls: int
    change_rate: float

    candidate_count: DistributionInfo
    final_count: DistributionInfo
    introduced_count: DistributionInfo
    reordered_count: DistributionInfo
    top_score: DistributionInfo

    # How deep into the candidate pool reranking reached: the tuning signal
    # for candidate_k.
    max_promoted_rank: DistributionInfo
    mean_promoted_rank: DistributionInfo
    unused_candidate_depth: DistributionInfo


class RetrievalResponse(BaseModel):
    window: WindowInfo
    retrievers: list[RetrieverInfo] = Field(default_factory=list)
    fusion: FusionInfo | None = None
    reranking: RerankingInfo | None = None

    # States plainly what this endpoint does not provide, so a client does
    # not have to infer it from absence.
    offline_metrics_available: bool = False
    offline_metrics_note: str = (
        "Recall@K, Precision@K, MRR and nDCG require an evaluation dataset "
        "with known-correct documents and are not derivable from production "
        "traffic."
    )


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class ErrorCountInfo(BaseModel):
    stage: str
    error_type: str
    count: int


class ErrorsResponse(BaseModel):
    window: WindowInfo
    failed_requests: int
    failure_rate: float
    by_stage: list[ErrorCountInfo] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Traces
# ----------------------------------------------------------------------


class TraceSummaryInfo(BaseModel):
    trace_id: str
    request_id: str | None = None

    route: str | None = None
    status: str
    status_code: int | None = None
    error_type: str | None = None

    started_at: datetime
    duration_ms: float

    conversation_id: str | None = None
    user_id: str | None = None

    environment: str | None = None
    app_version: str | None = None


class TraceListResponse(BaseModel):
    window: WindowInfo
    traces: list[TraceSummaryInfo] = Field(default_factory=list)

    # The started_at of the last row: pass it back as `before` for the next
    # page. Null when this is the final page.
    next_before: datetime | None = None


class SpanInfo(BaseModel):
    span_id: str
    parent_span_id: str | None = None

    # Waterfall position. Ordering by started_at does not work - the wall
    # clock ties between a parent and the child it opens.
    sequence: int

    stage: str
    status: str
    error_type: str | None = None

    started_at: datetime
    duration_ms: float

    metadata: dict = Field(default_factory=dict)


class TraceTokenInfo(BaseModel):
    stage: str
    model_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal | None = None


class KnowledgeBaseInfo(BaseModel):
    """What there is to retrieve from, as opposed to traffic against it."""

    documents_by_status: dict[str, int] = Field(default_factory=dict)
    total_documents: int = 0
    ready_documents: int = 0

    chunks_stored: int = 0
    chunks_retrievable: int = 0

    # Stored, vectors live, but invisible to lexical search because the
    # document is not ready. Zero is the healthy value.
    chunks_unreachable: int = 0

    last_ingested_at: datetime | None = None
    stalled_documents: int = 0
    healthy: bool = True


class IngestionResponse(BaseModel):
    window: WindowInfo
    knowledge_base: KnowledgeBaseInfo

    # Per-stage latency for the ingestion path only, newest window first.
    stages: list[StageLatencyInfo] = Field(default_factory=list)
    ingestions: int = 0
    failed_ingestions: int = 0

    # How long the sweep waits before calling an ingestion stalled, so the
    # panel can say what "stalled" means rather than asserting it.
    stall_threshold_minutes: int = 0


class TraceDetailResponse(BaseModel):
    trace: TraceSummaryInfo
    spans: list[SpanInfo] = Field(default_factory=list)

    # Every LLM call this request made, not just the answer.
    tokens: list[TraceTokenInfo] = Field(default_factory=list)
    total_tokens: int = 0
    estimated_cost_usd: Decimal | None = None


PerformanceResponse.model_rebuild()
