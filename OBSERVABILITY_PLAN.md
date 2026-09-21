# RAG Observability & Monitoring — Full Plan

Status of the observability upgrade, phase 1 through phase 19, plus the
evaluation work that was deliberately deferred.

Last updated: 2026-09-21. Phases 1–8 and 15–17 are merged to `main` and
deployed; phases 9–14 and 18–19 are not built.

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
| 9–11 | Offline evaluation, drift, experiment tracking | Deferred | — |
| 12 | Error taxonomy and rate-limit classification | Not built | — |
| 13 | Ingestion and knowledge-base monitoring | Not built | — |
| 14 | User feedback capture | Not built | — |
| 15 | Monitoring API | Done | #22 |
| 16 | Monitoring dashboard | Done | #23 |
| 17 | Trace explorer | Done | #24 |
| 18 | Alerting | Not built | — |
| 19 | Production hardening and retention enforcement | Not built | — |
| — | Stalled-ingestion recovery (found by phase 7) | Done | #27 |

Tests today: **419 backend** (`tests/unit` + `tests/api`, what CI runs) and
**125 engine** (`rag/tests/unit`).

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

# Part II — Remaining

Ordered as recommended, not by phase number.

## Phase 19 — Retention enforcement *(do first)*

**Why first:** `TELEMETRY_RETENTION_DAYS` is parsed, defaulted to 30 and
stored on the config object (`observability/config.py:75,100`) — and read by
nothing. There is no prune job and no delete of `rag_traces` or `rag_spans`
anywhere in the tree. Telemetry rows accumulate indefinitely on production
Postgres today.

A configuration knob that silently does nothing is worse than no knob,
because it reads as handled. This is simultaneously a cost problem and a
privacy one: the spec asked for retention to be configurable *and* enforced.

**Build:**

- `backend/services/telemetry_retention.py` —
  `prune_telemetry(session_factory, *, retention_days, now=None)`, deleting
  spans before traces, in bounded batches so a first run against a large
  table does not hold a long transaction.
- Call it from the lifespan alongside `recover_on_startup`, guarded the same
  way, and on a periodic timer thereafter.
- Index support on `started_at` if the delete plan needs it.
- Distinguish trace rows from span rows in the log line, so an operator can
  see what was reclaimed.

**Acceptance:** rows older than the window are gone after a startup; rows
inside it are untouched; a failure logs and does not stop the app; the
default of 30 days is honoured with no env var set.

Also in this phase: confirm no sampling gap under load, and document the
`capture_text` blast radius in `.env.example`.

## Phase 13 — Ingestion and knowledge-base monitoring

**Why:** the `Stage` enum already declares `INGESTION`, `INGESTION_BATCH`,
`DOCUMENT_EMBEDDING` and `VECTOR_UPSERT`
(`rag/src/rag/observability/schemas.py:41-44`) — and **nothing emits them**.
The enum promises coverage the pipeline does not have.

This is also the path the stalled-ingestion bug lived in. A span per batch
would have made that failure visible directly, rather than by inference from
a BM25 metric two phases away.

**Build:**

- Spans in `rag/ingestion/pipeline.py` around the ingest loop, each batch,
  embedding, and the Pinecone upsert. The tracer is already a no-op by
  default, so `rag/` stays runnable with no backend.
- A trace per ingestion in `backend/services/document_service.py`, carrying
  document id and filename (not the source path — that is the server's
  absolute upload path, dropped elsewhere for the same reason).
- Knowledge-base freshness: document count by status, chunk count, time since
  last successful ingest, count of documents currently stuck.
- `GET /api/monitoring/ingestion`, admin-only, plus the route classification
  table entry.
- A dashboard panel, reusing the phase 16 primitives.

**Acceptance:** an upload produces a trace whose waterfall shows per-batch
work; a killed ingest leaves a visibly incomplete trace; the freshness panel
names the stuck document that PR #27's sweep would mark failed.

## Phase 12 — Error taxonomy

**Why:** `/api/monitoring/errors` counts and groups failures but does not
classify them. A Gemini 429, a Pinecone timeout and a malformed PDF land in
one undifferentiated bucket, so the dashboard can say *that* things failed
but not *what kind* of failure is happening — which is the only thing that
changes what an operator does next.

**Build:**

- An error category enum in `rag/observability/schemas.py`: rate limit,
  upstream timeout, upstream unavailable, auth, validation, internal.
- Classification at the point where the exception is already caught, attached
  as span metadata. Classify by exception type and status code, not by
  matching message strings — provider messages carry keys and change without
  notice.
- Rate-limit specifics: which provider, which model, retry-after when the
  provider supplies it.
- Extend `/monitoring/errors` to break down by category, and the error panel
  with it.

**Acceptance:** a forced 429 is categorised as a rate limit and never as a
generic internal error; no provider message text reaches the database.

## Phase 14 — User feedback

**Why:** there is no table, no endpoint and no UI — `grep -rl feedback`
across `backend/src` and `frontend/src` returns nothing. This is the only
signal in the whole plan that carries a human judgement of answer quality,
and it is the input the deferred evaluation work would eventually need.

**Build:**

- Migration: `answer_feedback` — trace id, conversation id, user id, rating,
  optional free-text comment, created_at. Store the trace id so a rating
  joins to the retrieval and generation that produced it.
- `POST /api/feedback`, authenticated, ownership-checked, one rating per
  answer with update-in-place on a second submission.
- Thumbs up/down in the chat UI, on the assistant message.
- Aggregate into the dashboard: rating rate, positive share, and the ability
  to jump from a negative rating to its trace.

**Note:** free-text comments are user-entered content. They are deliberately
*not* telemetry metadata — they live in an application table with normal
retention, outside the sanitiser's path.

## Phase 18 — Alerting

**Why:** every metric an alert would fire on already exists. What is missing
is anything that evaluates them and says so.

**Build:**

- Thresholds in config, not code: error rate, p95 latency, cost per hour,
  queue-drop rate, time since last successful ingest.
- An evaluator on a timer reusing the phase 5 aggregation functions.
- Alert state with hysteresis, so a metric hovering at the threshold does not
  flap.
- Delivery: log first, then a webhook. Keep the delivery mechanism behind a
  protocol seam, like everything else in this project.
- Surface active alerts on the dashboard.

**Acceptance:** thresholds are configurable and documented in `.env.example`;
an alert clears on its own; a failing delivery cannot stop the evaluator or
the app.

## Phases 9–11 — Offline evaluation, drift, experiment tracking *(deferred)*

Deferred on purpose, and still correctly deferred.

These are the metrics that need **ground truth**: Recall@K, Precision@K, MRR,
nDCG, answer faithfulness, groundedness. Production retrieval logs cannot
yield them — the spec was explicit that these must not be faked from online
data, and nothing built so far pretends otherwise.

The prerequisite is a labelled evaluation set: questions with known relevant
chunks, drawn from this actual corpus. That is a content task before it is an
engineering task. Phase 14's feedback is the cheapest path to a first
labelled set.

When it does happen, it belongs in `rag/evaluation/` (which already exists),
run as an offline job against a fixed set — never in the request path, and
never mixed into the operational dashboard, because the two answer different
questions and carry different confidence.

---

## Recommended order

**19 → 13 → 12 → 14 → 18 → 9–11**

19 is small, it affects production today, and it closes a gap that currently
misrepresents itself as closed. 13 next, because ingestion is the last
pipeline running blind and is where a real incident already lived. 12 and 14
add signal the dashboard cannot currently show. 18 is worth little until 12
exists, since alerting on an undifferentiated error bucket produces noise.
The evaluation block stays last, gated on ground truth rather than on
engineering time.

---

## Appendix

**Migrations added by this work:** `0005_telemetry`,
`0006_telemetry_dimensions`, `0007_span_sequence`, `0008_token_cost`,
`0009_ingest_heartbeat`.

**Configuration** (all defaulted; see `backend/.env.example`):
`TELEMETRY_ENABLED`, `TELEMETRY_SAMPLE_RATE`, `TELEMETRY_QUEUE_SIZE`,
`TELEMETRY_BATCH_SIZE`, `TELEMETRY_FLUSH_INTERVAL_SECONDS`,
`TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS`, `TELEMETRY_CAPTURE_TEXT`,
`TELEMETRY_RETENTION_DAYS` *(parsed but not yet enforced — phase 19)*,
`APP_ENVIRONMENT`, `APP_VERSION`, `INGEST_STALL_MINUTES`.

**Test files added by this work:** `rag/tests/unit/test_observability.py`,
`rag/tests/unit/test_metering.py`, `backend/tests/unit/test_telemetry.py`,
`backend/tests/unit/test_telemetry_repository.py`,
`backend/tests/unit/test_aggregation.py`,
`backend/tests/unit/test_retrieval_metrics.py`,
`backend/tests/unit/test_ingest_recovery.py`,
`backend/tests/api/test_monitoring_routes.py`.
