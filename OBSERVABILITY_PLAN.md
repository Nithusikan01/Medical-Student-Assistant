# RAG Observability & Monitoring — Full Plan

Status of the observability upgrade, phase 1 through phase 19, plus the
evaluation work that was deliberately deferred.

Last updated: 2026-09-21. **Every phase is built and merged to `main`.**
What follows is what each one did and why, kept as the record rather than
as a to-do list.

This plan instruments an application that already worked. Nothing here
redesigns the RAG pipeline — no retriever, vector store, embedder, reranker
or LLM integration was replaced, and the only changes to working code paths
were the ones instrumentation genuinely required.

---

## Ground rules

These came from the specification and constrain every phase, built or not:

1. **Instrument, don't rebuild.** The pipeline stays as it is.
2. **Monitoring failure ≠ RAG failure.** Telemetry is best-effort,
   asynchronous and exception-isolated. A broken recorder, a full queue or
   an unserialisable value must never turn a working answer into a 502.
3. **Online operational metrics are not offline evaluation metrics.**
   Production retrieval logs alone do not yield Recall@K or Precision@K —
   those need ground truth. Never invent a metric the available data cannot
   support.
4. **Monitoring must not become a source of data leakage.** No passwords,
   API keys, tokens, PII, raw prompts, raw responses or system prompts
   stored without cause; secrets never in logs, telemetry, trace metadata or
   dashboard responses.
5. **Pricing, thresholds and retention are configuration, not constants.**
6. **Do not expose internal implementation details to users.**

---

## Status at a glance

| Phase | Scope | Status | PR |
|------:|-------|--------|----|
| 1 | Read-only audit of the existing pipeline | Done | — |
| 2 | Telemetry architecture (engine-side tracer) | Done | #14 |
| 3 | End-to-end request tracing (ASGI middleware) | Done | #14 |
| 4 | Per-stage pipeline spans | Done | #15 → #19 |
| 5 | Operational metrics from trace/span rows | Done | #16 → #19 |
| 6 | Token metering and cost attribution | Done | #25 |
| 7 | Retrieval behaviour metrics | Done | #20 |
| 8 | Reranking depth and promotion profile | Done | #21 |
| 9–11 | Offline evaluation, drift, experiment tracking | Done | #34 |
| 12 | Error taxonomy and rate-limit classification | Done | #31 |
| 13 | Ingestion and knowledge-base monitoring | Done | #30 |
| 14 | User feedback capture | Done | #32 |
| 15 | Monitoring API | Done | #22 |
| 16 | Monitoring dashboard | Done | #23 |
| 17 | Trace explorer | Done | #24 |
| 18 | Alerting | Done | #33 |
| 19 | Production hardening and retention enforcement | Done | #29 |
| — | Stalled-ingestion recovery (found by phase 7) | Done | #27 |

Tests today: **542 backend** (`tests/unit` + `tests/api`, what CI runs) and
**200 engine** (`rag/tests/unit`).

---

# Part I — Delivered

## Phase 1 — Audit

Read-only. Established what the pipeline already did, where the seams were,
and which metrics the existing data could and could not support. No code
changed. The conclusion that shaped everything after it: the engine (`rag/`)
must not learn about databases or HTTP, so telemetry enters through the same
kind of protocol seam the project already used for `ConversationStore` and
`ChunkSink`.

## Phase 2 — Telemetry architecture

**Package:** `rag/src/rag/observability/`

- `schemas.py` — `Stage`, `SpanStatus`, `SpanRecord`, `TraceRecord`. The
  `Stage` enum lists only stages that actually exist in this pipeline.
- `protocol.py` — `TraceRecorder`, a structural Protocol (`record_span` /
  `record_trace`). The engine defines it; the application implements it.
  `rag/` keeps its rule of importing no `backend`, no `fastapi`, no
  `sqlalchemy`.
- `context.py` — `TraceContext` plus contextvars for the ambient trace, span
  and stage. Contextvars rather than a new parameter on every signature,
  which would have been exactly the invasive change the spec ruled out.
  anyio copies the context into FastAPI's worker thread, so this survives the
  synchronous `def` routes this app uses.
- `tracer.py` — `Tracer.trace()` / `.span()` / `.annotate()`. Every operation
  that could raise is guarded and degrades to a non-recording handle.
  `NULL_SPAN` / `NULL_TRACE` are shared singletons, so an unsampled request
  allocates nothing.
- `sanitize.py` — key-based redaction applied to all metadata before it
  leaves the process.

**Decision worth keeping:** the default recorder records nothing, so
`Tracer()` is a working no-op and every existing test runs untouched with no
telemetry setup.

## Phase 3 — Request tracing

**Package:** `backend/src/backend/observability/`

- `middleware.py` — `TelemetryMiddleware`, pure ASGI rather than
  `BaseHTTPMiddleware` (which would break contextvar propagation). Health
  checks are excluded. Each response carries `x-trace-id`.
- `sink.py` — `BackgroundTelemetrySink`: bounded queue plus a single daemon
  writer thread. A full queue drops; it does not block the request.
- `recorder.py` — the `TraceRecorder` implementation bridging the engine to
  the sink.
- `config.py` — ten `TELEMETRY_*` / `APP_*` settings, all with defaults.
  `TELEMETRY_CAPTURE_TEXT` defaults to **False**: raw prompts and responses
  are off unless someone deliberately turns them on.
- `inflight.py` — live in-flight request tracking.

**Migration 0005** — `rag_traces` / `rag_spans`. No foreign keys to
application tables (telemetry must never block an application write), `Float`
durations, OTel-shaped 32-hex string ids so these rows can be handed to an
exporter later without re-keying anything.

## Phase 4 — Pipeline spans

Spans opened at every real stage of the query path: memory load, query
rewrite, retrieval (dense, BM25, fusion), reranking, context build,
generation, memory write, summarization.

**Migration 0006** promotes `status_code` and `route` out of the JSON
metadata blob into real columns, because every dashboard query filtered on
them.

**Bug fixed here:** the sanitiser was matching a bare `"token"` substring and
redacting `prompt_tokens` / `total_tokens` — the very numbers phase 6 depends
on. Replaced with three-part matching: exact keys, markers, suffixes.

## Phase 5 — Operational metrics

`backend/observability/aggregation.py` — pure metric maths, no database and
no HTTP, so it is unit-testable in isolation: `percentile`,
`summarize_latency`, `summarize_requests`, `summarize_stages`,
`bucket_series`. `_is_failure` counts three distinct cases rather than
assuming a 5xx is the only way to fail.

## Phase 6 — Token metering and cost

`rag/src/rag/llm/metering.py` — `UsageEvent`, `UsageCollector`,
`collect_usage()`, `MeteredGenerator`. Wrapping the generator **once at the
composition root** meters all four LLM call sites with no signature changes
anywhere.

**Migration 0007** adds a monotonic per-trace `sequence` to spans.
Discovered because span `started_at` values *tie*: the wall clock is coarser
than the gap between a parent span and the child it opens, so waterfalls
rendered scrambled.

**Migration 0008** adds `model_pricing` plus `stage` / `trace_id` /
`user_id` / `estimated_cost_usd`. Pricing is a table, not a constant.

**Measured before and after:** 1291 tokens recorded against 1441 actually
spent — a 10.4% undercount — then fixed. Stage binding happens whether or not
a trace is sampled, so what a request costs never depends on whether it
happened to be sampled.

**Open item:** `model_pricing` is empty in production by design. Cost
displays "not priced" until `backend/scripts/seed_model_pricing.py` is run
with verified rates. "Not priced" is kept distinct from zero throughout.

## Phase 7 — Retrieval metrics

`backend/observability/retrieval_metrics.py` — per-retriever distributions,
fusion overlap, and a report assembled from span metadata.

**This phase found a real bug.** It reported `bm25 empty on 100% of calls`,
which led to the stalled-ingestion incident described below — the monitoring
work surfacing the class of failure it exists to surface.

## Phase 8 — Reranking depth

`rag.observability.metrics.promotion_profile` — how deep into the candidate
pool reranking actually reaches, plus `summarize_scores`, `rank_change`, and
`generation_metadata` (which surfaces `latency` and `attempt`, previously
discarded).

## Phase 15 — Monitoring API

`backend/routers/monitoring.py`, seven admin-only endpoints:

```
GET /api/monitoring/overview
GET /api/monitoring/performance
GET /api/monitoring/tokens
GET /api/monitoring/retrieval
GET /api/monitoring/errors
GET /api/monitoring/traces
GET /api/monitoring/traces/{trace_id}
```

`resolve_window` accepts either a named range or explicit start/end (naive
timestamps read as UTC). Trace listing is cursor-paginated. The route
classification table in `backend/tests/api/test_route_protection.py` was
updated in the same commit, as the project requires.

## Phase 16 — Monitoring dashboard

`frontend/src/pages/AdminMonitoringPage.tsx` with
`components/monitoring/{Primitives,Charts,Waterfall}.tsx`. Recharts,
lazy-loaded. All three admin pages are lazy-loaded so the chat bundle does
not carry them.

Palette validated for CVD safety in OKLab. That validation changed an
*encoding*, not just colour steps: a 4xx is not a service status, so it takes
a categorical violet and red stays reserved for actual failures (ΔE 22.7/23.0
against the alternative's 4.0–5.7). Recharts' default of colouring legend
text with the series colour was replaced with a hand-rendered ink legend.

## Phase 17 — Trace explorer

`AdminTracesPage.tsx` and `AdminTraceDetailPage.tsx`: a filterable trace list
and a per-trace waterfall, hand-rolled in CSS, ordered by the phase 6
sequence rather than by timestamp.

## Out of band — stalled-ingestion recovery (PR #27)

Not a spec phase; found by phase 7's metric.

`DocumentService` marks a document `failed` when ingestion *raises* — which
covers every failure the process survives and none where the process itself
goes away. A killed uvicorn raised nothing, so a document sat in `processing`
permanently: its chunks invisible to BM25 (the lexical index is built from
`ready` documents only) while its vectors stayed live in Pinecone. Hybrid
retrieval silently degraded to dense-only.

**Migration 0009** adds `documents.heartbeat_at`, touched as each batch
lands. `updated_at` could not serve — ingestion writes to `document_chunks`,
not `documents`, so a healthy twenty-minute ingest and one that died ten
seconds in look identical through it.

`backend/services/ingest_recovery.py` sweeps at startup — exactly when the
replacement for a killed process comes up — guarded so it cannot stop the app
booting. Documents are marked **failed, not repaired** (partial chunk rows
promoted to `ready` would be undetectable downstream) and chunks are **left
in place** (the admin's call; the delete path already removes them). A live
ingest has a recent heartbeat and is left alone, which is what makes the
sweep safe with several ECS tasks running.

---

# Part II — The second half

Built in the order 19 → 13 → 12 → 14 → 18 → 9–11, chosen by what was
wrong rather than by phase number.

## Phase 19 — Retention enforcement (PR #29)

**Why it went first:** `TELEMETRY_RETENTION_DAYS` had been parsed,
defaulted to 30 and read by nothing since the telemetry tables shipped.
A configuration knob that silently does nothing is worse than no knob,
because it reads as handled — and `rag_spans` was growing without bound
on production while the setting said otherwise.

`backend/services/telemetry_retention.py` deletes traces past the window
and their spans with them, in committed batches, once at startup and then
every `TELEMETRY_RETENTION_INTERVAL_HOURS`.

Two ordering decisions:

- **Spans are deleted by `trace_id`, never by their own timestamp.** A
  long request can start before the cutoff and emit spans after it;
  sweeping by age would delete the trace and strand the rest of its
  waterfall.
- **Orphan spans are swept separately, and only once no trace below the
  cutoff is left.** They are a real state: the sink drops on a full queue
  and writes the trace last, so a burst leaves spans whose trace never
  arrived. A span cannot start before its trace, so anything older than
  the cutoff at that point is an orphan — but that argument only holds
  once the trace sweep has drained, which is why the orphan pass is gated
  on it.

**Migration 0010** indexes `rag_spans.started_at`; the existing
`(stage, started_at)` composite cannot serve the orphan query. Retention
runs whether or not telemetry is enabled, so turning capture off lets what
was already captured age out.

## Phase 13 — Ingestion and knowledge-base monitoring (PR #30)

The `Stage` enum had declared `INGESTION`, `INGESTION_BATCH`,
`DOCUMENT_EMBEDDING` and `VECTOR_UPSERT` since telemetry shipped, and
nothing emitted any of them. The enum promised coverage the pipeline did
not have — which is how an ingest that died mid-run could only be found by
inference from a retrieval metric two phases away.

The pipeline now opens a span per document, per batch, per embedding call
and per upsert, plus `DOCUMENT_LOAD` for the PDF parse. They nest under
the trace the middleware already opened for `POST /api/ingest`. Chunking
deliberately gets no span: `chunk_batches` is a generator, so a span
around the loop would re-time the whole ingestion under a name claiming to
be chunking.

`GET /api/monitoring/ingestion` answers two questions on purpose — the
knowledge-base half is a snapshot and ignores the window, the stage half
is windowed like every other latency panel.

The number worth having is **chunks stored minus chunks a lexical search
can reach**. BM25 is built from `ready` documents only, so a stuck
document keeps its rows and its vectors while dropping out of half of
hybrid retrieval. That is the incident this application already had; it is
now a subtraction rather than an inference.

## Phase 12 — Error taxonomy (PR #31)

`/monitoring/errors` could say how many requests failed and where. It
could not say what kind of failure it was, which is the only part that
changes what an operator does next.

Classification is by exception type and status code, **never** by matching
message text. Provider messages change without notice, and they routinely
echo the key the request was sent with — a classifier that reads them is
one careless log line away from storing a credential.

It happens in `Tracer.mark_error`, which every span and trace already
passes through, so all four LLM call sites, both retrievers, the reranker
and the whole ingestion path are covered without one call site changing.

Retry-after is captured when a provider offers one; absent stays null
rather than zero, because zero renders as "retry immediately".
**Migration 0011** adds the column; existing rows read as `unclassified`
rather than being folded into `internal`.

## Phase 14 — User feedback (PR #32)

The only human judgement of quality in the application. Thumbs on each
answer, one rating per person per answer, the same thumb again withdraws
it.

`conversation_messages` gained `trace_id`, written from the **ambient
trace context** — no caller passes it and no signature changed. It is what
turns "this answer was wrong" into a waterfall an admin can open. The id
is copied onto the feedback row rather than joined for, because telemetry
ages out on its own schedule and a rating outlives the spans it points at.

Unlike the telemetry tables, `answer_feedback` carries real foreign keys:
it is written synchronously by a user looking at the message, so there is
no batching and no arrival-order problem. Free-text comments are
deliberately **not** telemetry metadata — they live under ordinary
retention, outside the sanitiser's path, never on a span.
**Migration 0012.**

## Phase 18 — Alerting (PR #33)

Every number an alert fires on already existed; nothing looked at them.

- **Thresholds are configuration.** Error rate, p95, spend, dropped
  telemetry, lexical silence and stuck ingestion.
- **A rate needs enough samples.** One request failing out of one is a
  100% error rate. Below the floor a rule reports `insufficient_data` —
  deliberately not `ok`, because collapsing the two would let a service
  that stopped receiving traffic look perfectly well.
- **Alerts clear at 80% of where they fire**, so a metric on the line
  cannot flap.
- **Only what starts firing is delivered.** Re-sending everything
  currently wrong on every tick is how an alerting system gets muted.

The endpoint reads the evaluator's last verdict rather than evaluating on
request. Delivery is behind a protocol — logging always, webhook when
configured — and a failing sink cannot stop the evaluator. One of the
rules is the failure this upgrade found once already: lexical retrieval
returning nothing while nothing raises.

## Phases 9–11 — Offline evaluation, drift, experiments (PR #34)

Deferred through the whole upgrade, and the reason held throughout: these
need **ground truth**. `rag/src/rag/evaluation/` now computes Recall@K,
Precision@K, MRR, nDCG and MAP against a labelled dataset, and none of it
is reachable from the dashboard or from any endpoint.

What the package does *not* do is the important part. It cannot be run
against production logs, and nothing in it will invent a number from them.
An unlabelled question is skipped and counted, never scored as a miss —
otherwise a set would report a worse system the larger it grew. Every
metric returns null rather than zero when it is undefined, and the mean
skips nulls instead of averaging them in.

`compare()` covers both remaining jobs with one mechanism: same dataset
and different config is an **experiment**; same config and different
numbers is **drift**, meaning the corpus moved underneath. It says which
it looks like rather than leaving that to be inferred, and refuses to
compare reports from different datasets — the subtraction would work and
the answer would be meaningless, which is the more dangerous kind of
wrong.

Run with `backend/scripts/evaluate_retrieval.py`. The retriever comes from
`build_hybrid_retriever()`, extracted from the composition root so
evaluation measures the system actually running rather than a separately
assembled one.

**Still required before any of these numbers mean anything: somebody has
to write the labelled set.** `backend/data/evaluation/example.json` is a
template with no labels in it.

---

## What this upgrade found

Worth recording, because it is the argument for having done it:

- **A document stuck in `processing` for good**, its 1,056 chunks
  invisible to BM25 while its vectors stayed live in Pinecone. Hybrid
  retrieval had silently degraded to dense-only. Found by phase 7's
  `bm25 empty 100%`, fixed in PR #27, and now alerted on directly.
- **A 10.4% token undercount** — 1,291 recorded against 1,441 actually
  spent, because only the final generation call was metered.
- **Waterfalls rendering scrambled**, because span `started_at` values
  tie: the wall clock is coarser than the gap between a parent span and
  the child it opens.
- **A sanitiser redacting `prompt_tokens`** on a bare `token` substring
  match — the very numbers the cost work depends on.
- **Two settings that did nothing**: `TELEMETRY_RETENTION_DAYS`, and four
  ingestion stages declared in an enum nothing emitted.

## Appendix

**Migrations added by this work:** `0005_telemetry`,
`0006_telemetry_dimensions`, `0007_span_sequence`, `0008_token_cost`,
`0009_ingest_heartbeat`, `0010_span_started_at_index`,
`0011_error_category`, `0012_answer_feedback`.

**Configuration** (all defaulted; `backend/.env.example` documents each one
and when to move it):

- Telemetry — `TELEMETRY_ENABLED`, `TELEMETRY_SAMPLE_RATE`,
  `TELEMETRY_QUEUE_SIZE`, `TELEMETRY_BATCH_SIZE`,
  `TELEMETRY_FLUSH_INTERVAL_SECONDS`,
  `TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS`, `TELEMETRY_CAPTURE_TEXT`,
  `TELEMETRY_RETENTION_DAYS`, `TELEMETRY_RETENTION_INTERVAL_HOURS`,
  `APP_ENV`, `APP_VERSION`.
- Ingestion — `INGEST_STALL_MINUTES`.
- Alerts — `ALERTS_ENABLED`, `ALERT_ERROR_RATE`, `ALERT_P95_MS`,
  `ALERT_COST_PER_HOUR_USD`, `ALERT_DROPPED_RECORDS`,
  `ALERT_BM25_EMPTY_RATE`, `ALERT_MIN_REQUESTS`,
  `ALERT_INTERVAL_SECONDS`, `ALERT_WINDOW_MINUTES`, `ALERT_WEBHOOK_URL`.

**API surface added** (all admin-only except the last two):
`/api/monitoring/overview`, `/performance`, `/tokens`, `/retrieval`,
`/errors`, `/ingestion`, `/feedback`, `/alerts`, `/traces`,
`/traces/{trace_id}` — plus `POST /api/feedback` and
`DELETE /api/feedback/{message_id}`, which any authenticated reader may
call for their own answers.

**Test files added by this work:** `rag/tests/unit/test_observability.py`,
`test_metering.py`, `test_ingestion_observability.py`,
`test_error_taxonomy.py`, `test_evaluation.py`;
`backend/tests/unit/test_telemetry.py`, `test_telemetry_repository.py`,
`test_telemetry_retention.py`, `test_aggregation.py`,
`test_retrieval_metrics.py`, `test_knowledge_base.py`,
`test_ingest_recovery.py`, `test_alerts.py`, `test_alerting_service.py`;
`backend/tests/api/test_monitoring_routes.py`,
`test_feedback_routes.py`.

**Two things still to do by hand**, neither of them code:

1. `backend/scripts/seed_model_pricing.py` has not been run against
   production, so `model_pricing` is empty and cost reads "not priced"
   rather than zero. That is the correct display for unpriced usage, but
   it means spend is not being tracked in currency yet.
2. Nobody has written a labelled evaluation set, so phases 9–11 have the
   machinery and no data. Phase 14's thumbs-down ratings, each carrying
   its trace id, are the cheapest route to a first one.
