"""
The monitoring API.

Admin-only, read-only, and built entirely on the aggregation modules rather
than on queries of its own - the arithmetic lives where it is testable
without HTTP, and this layer only shapes it for a client.

Every endpoint takes the same window parameters and echoes the resolved
window back, so a chart can label itself without re-deriving what it asked
for.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.db.repositories import documents as document_repo
from backend.db.repositories import telemetry as telemetry_repo
from backend.db.repositories import usage as usage_repo
from backend.dependencies import AdminUser, DbSession
from backend.observability.aggregation import (
    NAMED_RANGES,
    TimeWindow,
    UnknownTimeRangeError,
    bucket_series,
    summarize_requests,
    summarize_stages,
)
from backend.observability.inflight import IN_FLIGHT
from backend.observability.knowledge_base import INGESTION_STAGES
from backend.observability.knowledge_base import (
    build_report as build_knowledge_base_report,
)
from backend.observability.retrieval_metrics import (
    RETRIEVAL_STAGES,
    build_report,
)
from backend.schemas.monitoring import (
    DistributionInfo,
    ErrorCountInfo,
    ErrorsResponse,
    FusionInfo,
    InFlightInfo,
    IngestionResponse,
    KnowledgeBaseInfo,
    LatencyInfo,
    ModelSpendInfo,
    OverviewResponse,
    PerformanceResponse,
    RequestInfo,
    RerankingInfo,
    RetrievalResponse,
    RetrieverInfo,
    RouteCountInfo,
    SeriesPointInfo,
    SpanInfo,
    StageLatencyInfo,
    StageSpendInfo,
    TokensResponse,
    TraceDetailResponse,
    TraceListResponse,
    TraceSummaryInfo,
    TraceTokenInfo,
    WindowInfo,
)
from backend.services.ingest_recovery import stall_threshold

router = APIRouter()

MAX_TRACE_PAGE = 200


# ----------------------------------------------------------------------
# Window resolution
# ----------------------------------------------------------------------


def resolve_window(
    range: Annotated[
        str,
        Query(description=f"One of: {', '.join(NAMED_RANGES)}"),
    ] = "24h",
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
) -> TimeWindow:
    """
    The window every endpoint shares.

    A named range by default; an explicit start/end pair overrides it, which
    is section 45's "Custom". Naive datetimes are read as UTC rather than
    rejected - a client sending a bare ISO timestamp means UTC here, and
    failing the request over a missing suffix helps nobody.
    """

    if start is not None and end is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)

        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        if end <= start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="`end` must be after `start`.",
            )

        return TimeWindow(start=start, end=end)

    try:
        return TimeWindow.named(range)
    except UnknownTimeRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown range '{range}'. Use one of: {', '.join(NAMED_RANGES)}.",
        ) from exc


Window = Annotated[TimeWindow, Depends(resolve_window)]


def window_info(window: TimeWindow) -> WindowInfo:
    return WindowInfo(
        start=window.start,
        end=window.end,
        bucket_seconds=int(window.bucket_size().total_seconds()),
    )


# ----------------------------------------------------------------------
# Converters
#
# The metric layer returns plain dataclasses; these turn them into response
# models without letting pydantic leak back into the aggregation code.
# ----------------------------------------------------------------------


def latency_info(summary) -> LatencyInfo:
    points = summary.percentiles

    return LatencyInfo(
        count=summary.count,
        p50_ms=points.get("p50"),
        p75_ms=points.get("p75"),
        p90_ms=points.get("p90"),
        p95_ms=points.get("p95"),
        p99_ms=points.get("p99"),
    )


def request_info(summary) -> RequestInfo:
    return RequestInfo(
        total=summary.total,
        succeeded=summary.succeeded,
        client_errors=summary.client_errors,
        failed=summary.failed,
        success_rate=summary.success_rate,
        client_error_rate=summary.client_error_rate,
        failure_rate=summary.failure_rate,
        requests_per_minute=summary.requests_per_minute,
        latency=latency_info(summary.latency),
    )


def stage_info(summary) -> StageLatencyInfo:
    return StageLatencyInfo(
        stage=summary.stage,
        count=summary.count,
        errors=summary.errors,
        error_rate=summary.error_rate,
        latency=latency_info(summary.latency),
    )


def distribution_info(distribution) -> DistributionInfo:
    return DistributionInfo(
        count=distribution.count,
        mean=distribution.mean,
        p50=distribution.p50,
        p95=distribution.p95,
        minimum=distribution.minimum,
        maximum=distribution.maximum,
    )


def trace_summary(trace) -> TraceSummaryInfo:
    return TraceSummaryInfo(
        trace_id=trace.id,
        request_id=trace.request_id,
        route=trace.route,
        status=trace.status,
        status_code=trace.status_code,
        error_type=trace.error_type,
        started_at=trace.started_at,
        duration_ms=trace.duration_ms,
        conversation_id=str(trace.conversation_id) if trace.conversation_id else None,
        user_id=str(trace.user_id) if trace.user_id else None,
        environment=trace.environment,
        app_version=trace.app_version,
    )


def _total_cost(rows, index: int, priced_index: int) -> tuple[Decimal | None, bool]:
    """
    Sum a cost column, keeping "nothing was priced" distinct from "cost 0".
    """

    priced = sum(int(row[priced_index] or 0) for row in rows)

    if not priced:
        return None, False

    total = sum(Decimal(row[index] or 0) for row in rows)

    return total, True


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------


@router.get("/monitoring/overview", response_model=OverviewResponse)
def overview(session: DbSession, admin: AdminUser, window: Window) -> OverviewResponse:
    traces = telemetry_repo.trace_points(session, window)
    summary = summarize_requests(traces, window)

    stages = summarize_stages(telemetry_repo.span_points(session, window))

    totals = usage_repo.totals_between(session, window.start, window.end)
    cost, priced = _total_cost(totals["by_model"], 5, 6)

    errors = telemetry_repo.error_counts_by_type(session, window)

    return OverviewResponse(
        window=window_info(window),
        requests=request_info(summary),
        slowest_stages=[stage_info(stage) for stage in stages[:5]],
        in_flight=InFlightInfo(current=IN_FLIGHT.current, peak=IN_FLIGHT.peak),
        total_tokens=sum(int(row[4] or 0) for row in totals["by_model"]),
        estimated_cost_usd=cost,
        pricing_configured=priced,
        error_count=sum(count for _, _, count in errors),
    )


@router.get("/monitoring/performance", response_model=PerformanceResponse)
def performance(
    session: DbSession,
    admin: AdminUser,
    window: Window,
    route: Annotated[str | None, Query()] = None,
) -> PerformanceResponse:
    traces = telemetry_repo.trace_points(session, window, route=route)

    return PerformanceResponse(
        window=window_info(window),
        requests=request_info(summarize_requests(traces, window)),
        stages=[
            stage_info(stage)
            for stage in summarize_stages(telemetry_repo.span_points(session, window))
        ],
        series=[
            SeriesPointInfo(
                start=bucket.start,
                total=bucket.total,
                succeeded=bucket.succeeded,
                client_errors=bucket.client_errors,
                failed=bucket.failed,
                p95_ms=bucket.p95_ms,
            )
            for bucket in bucket_series(traces, window)
        ],
        routes=[
            RouteCountInfo(route=name, count=count)
            for name, count in telemetry_repo.route_counts(session, window)
        ],
    )


@router.get("/monitoring/tokens", response_model=TokensResponse)
def tokens(session: DbSession, admin: AdminUser, window: Window) -> TokensResponse:
    totals = usage_repo.totals_between(session, window.start, window.end)

    by_model = totals["by_model"]
    cost, priced = _total_cost(by_model, 5, 6)

    return TokensResponse(
        window=window_info(window),
        total_tokens=sum(int(row[4] or 0) for row in by_model),
        prompt_tokens=sum(int(row[2] or 0) for row in by_model),
        completion_tokens=sum(int(row[3] or 0) for row in by_model),
        estimated_cost_usd=cost,
        pricing_configured=priced,
        by_model=[
            ModelSpendInfo(
                model_id=row[0],
                provider=row[1],
                prompt_tokens=int(row[2] or 0),
                completion_tokens=int(row[3] or 0),
                total_tokens=int(row[4] or 0),
                estimated_cost_usd=Decimal(row[5]) if row[6] else None,
                priced_calls=int(row[6] or 0),
                calls=int(row[7] or 0),
            )
            for row in by_model
        ],
        by_stage=[
            StageSpendInfo(
                stage=row[0],
                total_tokens=int(row[1] or 0),
                estimated_cost_usd=Decimal(row[2]) if row[2] is not None else None,
                calls=int(row[3] or 0),
            )
            for row in totals["by_stage"]
        ],
    )


@router.get("/monitoring/retrieval", response_model=RetrievalResponse)
def retrieval(
    session: DbSession,
    admin: AdminUser,
    window: Window,
) -> RetrievalResponse:
    report = build_report(
        telemetry_repo.span_metadata(session, window, stages=RETRIEVAL_STAGES)
    )

    return RetrievalResponse(
        window=window_info(window),
        retrievers=[
            RetrieverInfo(
                stage=r.stage,
                calls=r.calls,
                empty_calls=r.empty_calls,
                empty_rate=r.empty_rate,
                result_count=distribution_info(r.result_count),
                top_score=distribution_info(r.top_score),
                average_score=distribution_info(r.average_score),
            )
            for r in report.retrievers
        ],
        fusion=(
            FusionInfo(
                calls=report.fusion.calls,
                dense_only_share=report.fusion.dense_only_share,
                bm25_only_share=report.fusion.bm25_only_share,
                overlap_share=report.fusion.overlap_share,
                single_retriever_calls=report.fusion.single_retriever_calls,
                single_retriever_rate=report.fusion.single_retriever_rate,
                overlap_count=distribution_info(report.fusion.overlap_count),
                unique_count=distribution_info(report.fusion.unique_count),
            )
            if report.fusion
            else None
        ),
        reranking=(
            RerankingInfo(
                calls=report.reranking.calls,
                reranker_usage=report.reranking.reranker_usage,
                degraded_calls=report.reranking.degraded_calls,
                degraded_rate=report.reranking.degraded_rate,
                changed_calls=report.reranking.changed_calls,
                change_rate=report.reranking.change_rate,
                candidate_count=distribution_info(report.reranking.candidate_count),
                final_count=distribution_info(report.reranking.final_count),
                introduced_count=distribution_info(report.reranking.introduced_count),
                reordered_count=distribution_info(report.reranking.reordered_count),
                top_score=distribution_info(report.reranking.top_score),
                max_promoted_rank=distribution_info(report.reranking.max_promoted_rank),
                mean_promoted_rank=distribution_info(
                    report.reranking.mean_promoted_rank
                ),
                unused_candidate_depth=distribution_info(
                    report.reranking.unused_candidate_depth
                ),
            )
            if report.reranking
            else None
        ),
    )


@router.get("/monitoring/errors", response_model=ErrorsResponse)
def errors(session: DbSession, admin: AdminUser, window: Window) -> ErrorsResponse:
    summary = summarize_requests(telemetry_repo.trace_points(session, window), window)

    return ErrorsResponse(
        window=window_info(window),
        failed_requests=summary.failed,
        failure_rate=summary.failure_rate,
        by_stage=[
            ErrorCountInfo(stage=stage, error_type=error_type, count=count)
            for stage, error_type, count in telemetry_repo.error_counts_by_type(
                session, window
            )
        ],
    )


@router.get("/monitoring/ingestion", response_model=IngestionResponse)
def ingestion(
    session: DbSession,
    admin: AdminUser,
    window: Window,
) -> IngestionResponse:
    """
    The corpus and the pipeline that fills it.

    Two different questions in one response, deliberately. The knowledge
    base half is a snapshot and ignores the window - "how much is
    retrievable right now" has no time range. The stage half is windowed
    like every other latency panel.
    """

    stored, retrievable = document_repo.chunk_totals(session)

    report = build_knowledge_base_report(
        status_counts=document_repo.status_counts(session),
        chunks_stored=stored,
        chunks_retrievable=retrievable,
        last_ingested_at=document_repo.last_ingested_at(session),
        stalled_documents=document_repo.count_processing_since(
            session,
            datetime.now(UTC) - stall_threshold(),
        ),
    )

    stages = summarize_stages(
        telemetry_repo.span_points(session, window, stages=INGESTION_STAGES)
    )

    # The top-level ingestion span stands for one document ingested, so its
    # count and error count are the document-level numbers; the nested
    # stages would count batches and overstate both.
    top_level = next(
        (summary for summary in stages if summary.stage == "ingestion"),
        None,
    )

    return IngestionResponse(
        window=window_info(window),
        knowledge_base=KnowledgeBaseInfo(
            documents_by_status=report.documents_by_status,
            total_documents=report.total_documents,
            ready_documents=report.ready_documents,
            chunks_stored=report.chunks_stored,
            chunks_retrievable=report.chunks_retrievable,
            chunks_unreachable=report.chunks_unreachable,
            last_ingested_at=report.last_ingested_at,
            stalled_documents=report.stalled_documents,
            healthy=report.healthy,
        ),
        stages=[stage_info(summary) for summary in stages],
        ingestions=top_level.count if top_level else 0,
        failed_ingestions=top_level.errors if top_level else 0,
        stall_threshold_minutes=int(stall_threshold().total_seconds() // 60),
    )


@router.get("/monitoring/traces", response_model=TraceListResponse)
def list_traces(
    session: DbSession,
    admin: AdminUser,
    window: Window,
    limit: Annotated[int, Query(ge=1, le=MAX_TRACE_PAGE)] = 50,
    before: Annotated[datetime | None, Query()] = None,
    route: Annotated[str | None, Query()] = None,
    failed_only: Annotated[bool, Query()] = False,
    conversation_id: Annotated[uuid.UUID | None, Query()] = None,
) -> TraceListResponse:
    rows = telemetry_repo.list_traces(
        session,
        window,
        limit=limit,
        before=before,
        route=route,
        failed_only=failed_only,
        conversation_id=conversation_id,
    )

    return TraceListResponse(
        window=window_info(window),
        traces=[trace_summary(row) for row in rows],
        # Only when the page was full: a short page is the last one, and
        # offering a cursor for it would send the client on a pointless
        # extra round trip.
        next_before=rows[-1].started_at if len(rows) == limit else None,
    )


@router.get("/monitoring/traces/{trace_id}", response_model=TraceDetailResponse)
def trace_detail(
    trace_id: str,
    session: DbSession,
    admin: AdminUser,
) -> TraceDetailResponse:
    """
    One request, end to end: the trace, its span waterfall, and every LLM
    call it made.

    This is what answers "why was this particular answer bad" from a single
    id - the acceptance criterion the whole upgrade is built around.
    """

    trace = telemetry_repo.get_trace(session, trace_id)

    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found.",
        )

    spans = telemetry_repo.spans_for_trace(session, trace_id)
    token_rows = usage_repo.tokens_for_trace(session, trace_id)

    priced = [row[5] for row in token_rows if row[5] is not None]

    return TraceDetailResponse(
        trace=trace_summary(trace),
        spans=[
            SpanInfo(
                span_id=span.id,
                parent_span_id=span.parent_span_id,
                sequence=span.sequence,
                stage=span.stage,
                status=span.status,
                error_type=span.error_type,
                started_at=span.started_at,
                duration_ms=span.duration_ms,
                metadata=span.meta or {},
            )
            for span in spans
        ],
        tokens=[
            TraceTokenInfo(
                stage=row[0],
                model_id=row[1],
                prompt_tokens=int(row[2]),
                completion_tokens=int(row[3]),
                total_tokens=int(row[4]),
                estimated_cost_usd=Decimal(row[5]) if row[5] is not None else None,
            )
            for row in token_rows
        ],
        total_tokens=sum(int(row[4]) for row in token_rows),
        estimated_cost_usd=sum(priced, Decimal(0)) if priced else None,
    )
