# Anamnesis

*Anamnesis* — the recollection of what came before; in clinical practice, the patient history
a physician takes before anything else. Named for what the application does: it remembers the
conversation and recalls the passage that answers the question.

A full-stack Retrieval Augmented Generation application for a class of medical students to ask
questions against a shared library of documents: a Python RAG engine, a FastAPI backend with
JWT authentication and PostgreSQL persistence, and a React + TypeScript web app. An admin
uploads and manages the PDF library; every signed-in user asks questions against it, with
their own private, resumable conversation history.

Retrieval is hybrid (dense + BM25, fused with Reciprocal Rank Fusion) and reranked; both
embedding and reranking run on Pinecone's hosted inference by default, so the deployed API
needs no PyTorch and downloads no model weights. The final answer comes from a
user-selectable model — Google Gemini by default, or one of the Groq-hosted open models when
a Groq key is configured. Conversation-aware query rewriting lets follow-up questions get
folded into standalone retrieval queries, a rolling summary keeps long chats bounded, and a
response cache serves a question the class has already asked without retrieving or generating
again.

Every request is traced end to end. An admin dashboard reports latency by pipeline stage,
token spend and estimated cost, retrieval behaviour, error categories, the state of the
corpus and reader ratings; a trace explorer answers "why was *this* answer bad" from a single
id; and a rule evaluator turns the same metrics into alerts. Retrieval *quality* — Recall@K,
MRR, nDCG — is measured separately and offline, against a labelled set, because production
traffic cannot produce it.

## Current Capabilities

### Asking and answering

- PDF text extraction with `pypdf`, recursive chunking with LangChain text splitters
- Dense embeddings and reranking through Pinecone's hosted inference
  (`llama-text-embed-v2` / `bge-reranker-v2-m3` by default), with local Sentence Transformer /
  cross-encoder models available as a fallback
- BM25 lexical retrieval with `rank-bm25`, sourced from the same Postgres chunk table that
  backs Pinecone, so ingesting or deleting a document updates both retrieval paths together
- Hybrid retrieval via Reciprocal Rank Fusion across dense and BM25 results
- Reranking that degrades instead of failing: Pinecone hosted reranking, falling back to the
  Gemini model on a hosted failure, then to unranked retrieval order
- Per-query model selection: Gemini through `google-genai`, or GPT-OSS 120B / GPT-OSS 20B /
  Qwen3.8 27B through Groq. Groq options are only offered when `GROQ_API_KEY` is set, and the
  response echoes back which model actually answered
- Conversations are private, persisted, and resumable across restarts and devices, with a
  checkpointed rolling summary so long chats don't re-summarize on every turn
- A two-tier response cache (exact text, then semantic similarity) keyed on the *rewritten*,
  context-free form of the question, so a class asking the same thing pays for retrieval and
  generation once
- Greetings, thank-yous and farewells are recognised and welcomed before retrieval runs, so
  "hi" is answered with an introduction rather than "I don't know based on the provided
  document" — anything not positively recognised as small talk still goes to the corpus
- Readers can rate an answer up or down, with an optional note; the rating is tied to the
  trace that produced the answer

### Accounts and administration

- Email/password registration and login with JWT access tokens and rotating, httpOnly-cookie
  refresh tokens (reuse detection revokes the whole token family)
- Two roles: `admin` (manages the shared document library, the user roster, and sees every
  monitoring surface) and `user` (asks questions, manages only their own conversations)
- Registration gated by an open-registration flag or an invite code, either is sufficient
- The first admin is seeded from environment variables on startup, idempotently
- Document lifecycle: admin-only upload (deduplicated by content hash), listing, deletion
  (BM25 refreshed before vectors are removed, so a document is never "delisted but still
  retrievable"), and an orphan-sweep purge endpoint for a delete that failed partway
- An ingest that stops without raising — most often a process restarted mid-upload — is
  reconciled rather than left stuck in `processing`: each batch touches a heartbeat, and a
  startup sweep plus a stall threshold mark the abandoned ones failed
- Admin user roster: list every registered user, promote/demote between `user` and `admin`,
  and delete accounts (deleting an admin needs an extra confirmation; the last admin cannot
  be demoted, and nobody can delete themselves)

### Monitoring and evaluation

- Every API request produces a trace, and every pipeline stage a span — memory load, query
  rewrite, cache lookup, dense/BM25/fusion/rerank, context build, generation, memory write,
  summarization, and the whole ingestion path
- Telemetry is best-effort by construction: a bounded queue and a background writer thread,
  so a monitoring failure or a full queue never turns a working answer into a 502 — and the
  dropped count is reported rather than hidden
- Admin monitoring API and dashboard: requests and error rate, latency by stage, token spend
  and estimated cost, retrieval and reranking behaviour, ingestion and corpus health,
  and reader feedback — all over a shared time window
- Trace explorer: filter by route, failure or conversation, then open one trace as a span
  waterfall with its per-stage token and cost breakdown
- Failures are classified by exception type and status code (rate limit, timeout, upstream,
  auth, validation, internal) rather than by matching message text, so the dashboard says
  what kind of problem it is and never stores a provider message
- An in-process alert evaluator reads the same metrics on a timer, applies thresholds with
  hysteresis and a minimum sample size, logs what starts firing, and can POST it to a webhook
- Token cost is priced at write time from a `model_pricing` table, so a later price change
  does not rewrite history; unpriced models read "not priced" rather than "$0.00"
- Telemetry rows age out on a configurable retention window, swept whether or not capture is
  currently enabled
- Offline retrieval evaluation (Recall@K, Precision@K, MRR, nDCG, MAP) against a labelled
  dataset, with saved runs and a comparison mode that distinguishes an experiment from drift

### Platform

- PostgreSQL persistence via SQLAlchemy 2.0 and Alembic (12 revisions): users, refresh
  tokens, invite codes, conversations and messages, the document/chunk registry, per-call
  token usage and cost, traces and spans, and answer feedback
- Ten FastAPI routers, every route deliberately classified as public, authenticated, or
  admin-only and enforced at `include_router()` level
- React + TypeScript web app: light/dark theme (chosen on the login screen, persisted per
  browser), login/register screens, a conversation sidebar, a model picker, per-answer source
  inspection and rating, and admin pages for the dashboard, documents, users and traces
- Docker image and GitHub Actions CI/CD (lint, tests, image build, migration-then-deploy)
- 782 tests across the engine and backend (233 + 549), all hermetic (SQLite, no network)

## Architecture

The ingestion path (admin-only, `POST /api/ingest`):

```text
PDF file
  -> DocumentLoader
  -> TextChunker
  -> Embedder (Pinecone hosted, or local Sentence Transformer)
  -> VectorDataProcessor
  -> PineconeVectorStore
  -> PostgresChunkSink -> document_chunks table
```

A `documents` row is created with `status=processing` before ingestion starts, so a crash
mid-upload leaves a visible, deletable row instead of orphaned vectors. Chunk text and
metadata land in `document_chunks`, which doubles as the BM25 corpus and the authoritative
list of Pinecone vector ids for that document. Each batch touches the row's `heartbeat_at`,
which is what lets a stalled ingest be told apart from a slow one. The document is flipped to
`ready` and the in-memory BM25 index is rebuilt in place once ingestion finishes, and the
response cache is emptied because the corpus it answered against has changed.

The query path (`POST /api/query`, any signed-in user):

```text
conversation_id + question (+ optional model)
  -> PersistentConversationMemory (Postgres-backed, per conversation)
  -> QueryRewriter (LLM call: folds conversation history into a standalone query)
       skipped on the opening turn, where there is no history to fold in
  -> ResponseCache lookup on the standalone query  --hit--> cached answer + sources, done
  -> HybridRetriever
       -> DenseRetriever -> Pinecone
       -> BM25Retriever  -> BM25Index (built from document_chunks)
       (fused via Reciprocal Rank Fusion)
  -> Reranker (Pinecone hosted -> Gemini fallback -> unranked order)
  -> PromptBuilder -> selected generator (Gemini or Groq)
  -> answer + structured sources
  -> ResponseCache stores the answer (only if the prompt carried no conversation history)
  -> token usage and cost recorded; messages persisted; summarized at the trigger
```

Conversation memory is deliberately split into two views: `messages` holds only the turns
since the last summary checkpoint (this is what drives the summarization trigger), while a
separate `_recent` window drives what actually goes into the prompt. Naively hydrating full
history into both would make the trigger permanently true past a dozen or so messages and
fire an extra Gemini call on every turn, forever.

Document deletion runs in a specific order for the same reason: BM25 is refreshed first
(lexical retrieval stops seeing the document immediately, and the response cache is emptied),
then Pinecone vectors are deleted in batches of at most 1000 (Pinecone's per-call cap), and
only then is the registry row removed. A failed vector delete leaves the row in a `deleting`
state that an admin can retry via `POST /api/documents/{id}/purge`, which also sweeps any
vector ids that share the document's id prefix but have no matching chunk row (Pinecone's
serverless tier does not support delete-by-metadata-filter, so this sweep, not a filtered
delete, is the recovery path).

### Generation model selection

Only the final answer is user-selectable. Query rewriting, conversation summarization, and
the reranker fallback always use the default Gemini generator, so switching models never
changes how retrieval behaves.

The catalog lives in `backend/wiring/rag_factory.py::_GENERATION_MODEL_SPECS`:

| id                  | label               | provider | backing model           |
| ------------------- | ------------------- | -------- | ----------------------- |
| `gemini-flash`      | Gemini (default)    | gemini   | `GENERATION_MODEL_NAME` |
| `groq-gpt-oss-120b` | GPT-OSS 120B (Groq) | groq     | `openai/gpt-oss-120b`   |
| `groq-gpt-oss-20b`  | GPT-OSS 20B (Groq)  | groq     | `openai/gpt-oss-20b`    |
| `groq-qwen3.8-27b`  | Qwen3.8 27B (Groq)  | groq     | `qwen/qwen3.8-27b`      |

`available_generation_models()` omits the Groq entries entirely when `GROQ_API_KEY` is unset,
rather than listing them and failing on first use, and `resolve_generator()` raises for an
unknown or unavailable id (a 400) instead of silently substituting a different model than the
one that was asked for. `rag/llm/protocol.py::TextGenerator` is the structural Protocol both
`GeminiGenerator` and `GroqGenerator` satisfy — the same seam as `ConversationStore` and
`ChunkSink`, which is why adding a provider touches nothing in the engine's service layer.

Selection is not persisted server-side: like `top_k`, the client resends it on every request
(the frontend remembers the last choice in `localStorage`).

### Response cache

`rag/cache/` holds answers already given, so a repeated question skips retrieval, reranking
and generation entirely. `build_response_cache()` wires an `InMemorySemanticCache` into the
service, or `None` when `RESPONSE_CACHE_ENABLED=false` — `None` rather than a do-nothing
cache, so an absent `cache_lookup` span means "caching is off" instead of "every question was
new".

Three rules carry the correctness, and changing any of them needs care:

1. **Keyed on the standalone query, never the raw question.** The lookup happens after the
   rewrite, because the rewritten query is context-free by construction — that is what makes
   it safe to hand one conversation's answer to another. Keying on the raw question would
   serve nonsense for a follow-up like "what about the second one?".
2. **Only answers generated with no conversation history are stored**
   (`RESPONSE_CACHE_STORE_CONTEXT_FREE_ONLY`, on by default). An answer written with a
   conversation in front of it can refer back to it ("as I said above"), and nothing can tell
   from the text whether it did. Later turns still read from the cache; they just do not
   write to it.
3. **A hit skips the work, never the record of it.** The assistant memory write and the
   summarization check run on hits and misses alike. Skipping them would leave the stored
   conversation disagreeing with what the user was shown.

The scope is (normalised question, `top_k`, `model_id`): a different model or a different
number of sources legitimately gives a different answer, so neither shares entries. Matching
is two-tier — a free normalised-text hash, then a cosine scan over stored question vectors
above `RESPONSE_CACHE_SIMILARITY_THRESHOLD` (0.95 by default, deliberately high: serving the
answer to a nearly identical question is worse than missing). A semantic miss hands its
embedding back to dense retrieval rather than embedding the same text twice.

Bounded by `RESPONSE_CACHE_MAX_ENTRIES` (LRU) and `RESPONSE_CACHE_TTL_SECONDS`, and emptied
whenever the corpus changes. It is per-process: two uvicorn workers keep two caches and a
restart keeps none. The cache never raises; a failure is a cache miss. A lookup records a
`cache_lookup` span with `hit`, `match`, `similarity` and `entry_count` — never the question
text — and a hit produces `llm_calls=0` and `total_tokens=0` on the trace, so the spend saving
shows up on the existing dashboards by itself.

### Observability

Instrumentation was added to an application that already worked, under one rule: a monitoring
failure is not a RAG failure. The tracer, the queue and the writer are all exception-isolated,
and a full queue drops records rather than slowing the request that produced them.

```text
request -> TelemetryMiddleware  (trace row, X-Trace-ID / X-Request-ID response headers)
             |
             +-> Tracer.span(stage)  per pipeline stage, nested, sequence-ordered
                    |
                    +-> bounded queue -> background writer thread -> rag_traces / rag_spans
```

The engine defines the record types and the recorder protocol (`rag/observability/`) and
knows nothing about the database; `backend/observability/` holds the middleware, the Postgres
sink, the aggregation arithmetic and the alert rules. The aggregation modules are pure
functions over rows, which is why they are unit-tested without HTTP, a clock, or a session.

Spans exist for the query path (`memory_load`, `query_rewrite`, `cache_lookup`, `retrieval`,
`query_embedding`, `dense_retrieval`, `bm25_retrieval`, `fusion`, `reranking`,
`context_build`, `generation`, `memory_write`, `summarization`) and for ingestion
(`ingestion`, `document_load`, `ingestion_batch`, `document_embedding`, `vector_upsert`). A
span is only created for work that really runs, so an empty stage in a trace means "did not
happen", never "not instrumented".

What gets stored is deliberately narrow: counts, scores, durations, model names and
configuration. Raw question and answer text is off by default (`TELEMETRY_CAPTURE_TEXT=false`),
and the sanitiser strips credentials by key name — it cannot tell that a question is personal,
which is exactly why the switch defaults off. Error classification reads exception types and
status codes, never message text, for the same reason: provider messages change without notice
and frequently echo the key they were sent with. The six categories are `rate_limit`,
`timeout`, `upstream`, `auth`, `validation` and `internal` — short on purpose, since a taxonomy
with thirty entries is one nobody reads.

`OBSERVABILITY_PLAN.md` in the repository root is the full record of this work: phases 1
through 19, what each did and why.

### Alerting

`backend/observability/alerts.py` is pure — it takes a snapshot of numbers and returns a
verdict. Gathering the snapshot and delivering the result live in `services/alerting.py`, on a
timer inside the API process. Six rules ship: error rate, p95 latency, spend per hour, dropped
telemetry records, empty lexical retrieval, and stalled ingestion. Every threshold is read
from the environment, because every default is wrong for somebody.

Two behaviours are worth knowing about. An alert clears at 80% of the threshold it fires on,
so a metric sitting on the line cannot flap. And a rate rule below `ALERT_MIN_REQUESTS`
reports `insufficient_data` rather than `ok`: one request failing out of one is a 100% error
rate, and paging someone for it teaches them to ignore the next one. Only what starts firing
is sent to `ALERT_WEBHOOK_URL`; re-sending everything currently wrong on every tick is how an
alerting system gets muted. With `ALERTS_ENABLED=false`, `/api/monitoring/alerts` reports "not
running", which is deliberately not the same as "nothing is wrong".

### Token usage and cost

Each generator reports the provider's own token counts on `LLMResponse.usage`, and
`HistoryAwareRAGService.answer_with_sources` takes an `on_usage` callback invoked once per
generation call — the engine stays storage-agnostic, exactly like `ChunkSink`. The query
router's callback writes one `generation_usage_events` row per call, stamped with the trace
and stage it belongs to.

One row per call, rather than a running counter, is what makes "today" and "this month" both
a plain `SUM(total_tokens) WHERE created_at >= window_start`: no reset job, and no drift
between the two windows. Cost is computed at write time from whichever `model_pricing` row was
in effect, so a later price change does not silently rewrite history — and until
`scripts/seed_model_pricing.py` has been run with rates checked against the providers' pricing
pages, `estimated_cost_usd` stays NULL and the dashboard reports "not priced" rather than a
confident "$0.00". The word "estimated" is literal throughout: these figures come from a table
this application maintains, not from a provider invoice.

`GET /api/usage/models` (admin-only) reports every catalog model — including ones not
currently available, so a Groq model's history stays visible if the key is later removed.
Daily limits are hardcoded per provider (Groq's published free-tier quotas; Gemini is billed
rather than quota-capped on this plan, so it has none), and the monthly figure is a derived
reference ceiling (daily × days in month) since Groq's quotas reset daily.

### Offline evaluation

`rag/evaluation/` computes Recall@K, Precision@K, MRR, nDCG and MAP against a labelled
dataset, and the separation from `backend/observability/` is the point:

- `backend/observability/` measures what happened — latency, spend, error rates, how many
  chunks came back. Derivable from production traffic, served live by the monitoring API.
- `rag/evaluation/` measures whether it was any good. Not derivable from production traffic at
  any volume: it needs questions paired with the passages that genuinely answer them, which
  only a person who knows the corpus can write. Nothing it produces reaches the dashboard, and
  no endpoint serves it.

```powershell
cd backend
python scripts\evaluate_retrieval.py data\evaluation\example.json
python scripts\evaluate_retrieval.py data\evaluation\example.json --save runs\before.json
python scripts\evaluate_retrieval.py --compare runs\before.json runs\after.json
```

The comparison covers both experiment tracking (same dataset, different config) and drift
(same config, corpus changed underneath), and reports which of the two it looks like rather
than leaving that to be inferred. `backend/data/evaluation/example.json` is a template with no
labels in it — unlabelled examples are skipped and counted, never scored as misses.

Labels are `document_chunks` ids, which are also the Pinecone vector ids, so re-chunking a
document invalidates every label pointing into it. Label at document level where a question is
answered by a whole document: it is cheaper, it survives re-ingestion, and it is scored
separately rather than mixed in with passage-level scores.

## Project Structure

The repository is a monorepo with three top-level parts, two of them installable Python
packages:

```text
Anamnesis/
|-- rag/                          # RAG engine (importable library, no HTTP, no database)
|   |-- pyproject.toml            # package: rag-engine
|   |-- src/rag/
|   |   |-- cache/                # ResponseCache protocol + InMemorySemanticCache
|   |   |-- config/               # Settings + per-component config dataclasses
|   |   |-- conversation/         # ConversationMemory, ConversationStore protocol,
|   |   |                         # SessionManager, query rewriting, summarization
|   |   |-- embeddings/           # PineconeEmbedder (hosted) + TextEmbedder protocol
|   |   |-- evaluation/           # labelled-set metrics, runner, saved-run comparison
|   |   |-- indexes/              # BM25Index (in-place .rebuild())
|   |   |-- ingestion/            # loader, chunker, embedder, pipeline, ChunkSink protocol
|   |   |-- llm/                  # GeminiGenerator, GroqGenerator, TextGenerator protocol,
|   |   |                         # prompt builder, LLMResponse/TokenUsage, metering
|   |   |-- observability/        # Stage/SpanRecord/TraceRecord, Tracer, recorder protocol,
|   |   |                         # error taxonomy, metadata sanitiser
|   |   |-- rerankers/            # pinecone (hosted), gemini, local cross-encoder, fallback
|   |   |-- retrieval/            # dense, bm25, hybrid (RRF), QueryService
|   |   |-- services/             # HistoryAwareRAGService
|   |   |-- utils/
|   |   `-- vectorstore/          # Pinecone store
|   `-- tests/
|       |-- fixtures/
|       |-- integration/          # touches real Pinecone/Gemini; skips without an env flag
|       `-- unit/                 # no external services
|-- backend/                      # FastAPI HTTP layer (runtime root)
|   |-- pyproject.toml            # package: rag-backend
|   |-- .env                      # credentials live here
|   |-- alembic.ini, migrations/  # 12 revisions, 0001_auth_tables .. 0012_answer_feedback
|   |-- data/raw/                 # source PDFs
|   |-- data/evaluation/          # labelled evaluation sets (example.json is a template)
|   |-- storage/                  # uploads/ (deleted after ingestion)
|   |-- deploy/                   # task-definition.json: the ECS baseline CI renders
|   |-- scripts/                  # ad-hoc smoke-test / maintenance / evaluation scripts
|   |-- src/backend/
|   |   |-- app.py                # create_app + lifespan (db, admin seeding, RAG service,
|   |   |                         # telemetry writer, retention worker, alert evaluator)
|   |   |-- dependencies.py       # current user, admin gate, DB session, model registry
|   |   |-- auth/                 # password hashing, JWT + refresh tokens, AuthService
|   |   |-- db/                   # SQLAlchemy models and repositories
|   |   |-- observability/        # middleware, telemetry sink, aggregation, retrieval
|   |   |                         # metrics, knowledge-base report, alert rules, in-flight
|   |   |-- routers/              # health, auth, conversations, ingest, documents, query,
|   |   |                         # users, feedback, usage, monitoring
|   |   |-- schemas/              # request/response models
|   |   |-- services/             # upload handling, document lifecycle, conversation store,
|   |   |                         # Postgres chunk sink, ingest recovery, pricing,
|   |   |                         # telemetry retention, alerting
|   |   `-- wiring/               # rag_factory: model catalog, the live RAG service,
|   |                             # cache, tracer and telemetry sink singletons
|   `-- tests/
|       |-- unit/                 # SQLite, no HTTP
|       |-- api/                  # through TestClient against the real app
|       `-- integration/          # touches real Pinecone/Gemini; skips without an env flag
`-- frontend/                     # React + TypeScript (Vite) web app
    |-- package.json
    |-- vite.config.ts            # proxies /api and /health to the backend
    `-- src/
        |-- api/                  # typed fetch client (client, auth, conversations,
        |                         # documents, users, usage, feedback, monitoring)
        |-- auth/                 # AuthContext, useAuth, single-flight token refresh
        |-- theme/                # ThemeContext, useTheme (light/dark, persisted)
        |-- components/           # ChatPanel, ConversationSidebar, ModelSelect, SourceList,
        |                         # RouteGuards (Protected/Admin), ThemeToggle, Icons,
        |                         # admin/ and monitoring/ (charts, waterfall, primitives)
        |-- pages/                # LoginPage, RegisterPage, ChatPage, AdminDocumentsPage,
        |                         # AdminUsersPage, AdminMonitoringPage, AdminTracesPage,
        |                         # AdminTraceDetailPage
        `-- hooks/                # useConversation, useGenerationModels
```

`backend` depends on `rag`; `rag` never imports `backend`, `fastapi`, or `sqlalchemy` — a
ruff `TID251` rule enforces this at lint time. `backend/` is the runtime root: `.env`,
`data/raw/`, and `storage/` are resolved relative to it, so run uvicorn, Alembic, and the
scripts from inside `backend/`. Where the engine needs persistence, storage or reporting
(conversation memory, the BM25 corpus, token accounting, telemetry), it depends on a protocol
or callback defined in `rag/` (`ConversationStore`, `ChunkSink`, `TelemetryRecorder`,
`on_usage`) whose database-backed implementation lives in `backend/`. `ResponseCache` is the
same seam pointed the other way: the implementation shipped in `rag/` is in-process, and a
shared one would live in `backend/` without the service changing.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer (for the frontend)
- A PostgreSQL database (this deploys to AWS RDS — see `AWS_DEPLOYMENT_PLAN.md`; any Postgres
  works for local development)
- Pinecone API key and index name
- Google Gemini API key
- Optional: a Groq API key, to offer the Groq-hosted models in the picker
- Network access for Pinecone, Gemini, and (only if `USE_HOSTED_INFERENCE=false`) model
  downloads

## Installation

Both Python packages are installed in editable mode. Install `rag` first, since `backend`
imports it.

From the project root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "./rag[dev]"
python -m pip install -e "./backend[dev]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./rag[dev]"
python -m pip install -e "./backend[dev]"
```

Then install the frontend dependencies:

```powershell
cd frontend
npm install
```

## Environment Variables

Copy the template and fill in your credentials:

```powershell
cd backend
Copy-Item .env.example .env
```

`backend/.env.example` documents every variable with its default and the reasoning behind it.
The frontend has its own optional `frontend/.env.example`, whose only knob is
`VITE_BACKEND_URL`. Both `.env` files are gitignored; the `.env.example` files are committed.

A minimal `backend/.env` looks like:

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=your_pinecone_index_name
GEMINI_API_KEY=your_gemini_api_key

DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
SECRET_KEY=generate-one-see-below

ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=a-long-password-at-least-12-characters
```

Generate `SECRET_KEY` with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Required variables:

- `PINECONE_API_KEY` / `PINECONE_INDEX_NAME`: Pinecone credentials; the index is created
  automatically if it doesn't exist, sized to the embedding model in use.
- `GEMINI_API_KEY`: Google Gemini API key. It backs generation, query rewriting,
  summarization, and the reranker fallback, so it is required even when users pick a Groq
  model for their answers.
- `DATABASE_URL`: a PostgreSQL connection string, `postgresql+psycopg://...`.
- `SECRET_KEY`: signs access tokens. At least 32 characters; treat it like a password, since
  changing it invalidates every issued access token. Use a different value in production than
  in local development.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD`: the first administrator, seeded on startup if no user with
  that email exists yet. An existing account's password is never overwritten by this, so
  rotating the live admin password does not get silently reset on the next deploy.
  `ADMIN_PASSWORD` must be at least 12 characters or seeding is skipped (logged as an error).

Optional — authentication and transport:

- `GROQ_API_KEY`: enables the Groq-backed generation models (GPT-OSS 120B/20B, Qwen3.8 27B) as
  user-selectable alternatives to Gemini. Left unset, those options are simply not offered by
  `GET /api/models`; any past usage still shows on the admin usage dashboard.
- `ALLOW_OPEN_REGISTRATION` (default `false`): when false, `POST /api/auth/register` requires
  a valid invite code. There is currently no admin API for creating invite codes — insert a
  row into the `invite_codes` table directly, or leave open registration on for a small,
  trusted class.
- `CORS_ORIGINS`: comma-separated allowed origins for the deployed frontend. Falls back to
  `http://localhost:5173` / `http://127.0.0.1:5173` for local development.
- `COOKIE_SECURE` (default `false`): set to `true` wherever the app is served over HTTPS, so
  the refresh cookie only travels encrypted. Leave `false` for local HTTP development.
- `ACCESS_TOKEN_TTL_MINUTES` (default `15`), `REFRESH_TOKEN_TTL_DAYS` (default `30`).
- `GOOGLE_CLIENT_ID`: reserved for a future Google sign-in; not currently wired up (see
  Known Limitations).

Optional — retrieval, chunking and generation:

- `USE_HOSTED_INFERENCE` (default `true`): embedding and reranking run through Pinecone's
  hosted API. Set to `false` to use local Sentence Transformer / cross-encoder models instead,
  which requires the `rag` package's `local-models` extra
  (`pip install -e "./rag[local-models]"`) and downloads PyTorch and model weights on first
  run.
- `HOSTED_EMBEDDING_MODEL` / `HOSTED_EMBEDDING_DIMENSION` / `HOSTED_RERANK_MODEL`: hosted
  model names. The embedding dimension is fixed by the model and a Pinecone index cannot be
  resized, so changing it means creating a new index and re-ingesting.
- `CHUNK_SIZE` / `CHUNK_OVERLAP`: PDF chunking controls.
- `CANDIDATE_K` / `DENSE_TOP_K` / `RERANKING_K` / `FINAL_CONTEXT_K` / `SIMILARITY_THRESHOLD`:
  retrieval tuning; note that `top_k` on the live query path comes from the request body, and
  `CANDIDATE_K` only applies to `DenseRetriever` calls that pass no explicit `top_k`.
- `GENERATION_MODEL_NAME` (default `gemini-3.1-flash-lite`): the model behind the
  `gemini-flash` catalog entry, and the one used for rewriting and summarization.
- `STORAGE_PATH` (default `storage`): holds `uploads/` before ingestion deletes them. Relative
  paths resolve against the working directory, so run the API and scripts from `backend/`.

Optional — response cache:

- `RESPONSE_CACHE_ENABLED` (default `true`): the whole cache. Off means no `cache_lookup`
  span at all, which is how the dashboard tells "caching is off" from "every question was new".
- `RESPONSE_CACHE_SEMANTIC_ENABLED` (default `true`): the second tier, which embeds a question
  that missed on exact text and compares it with the ones already answered.
- `RESPONSE_CACHE_SIMILARITY_THRESHOLD` (default `0.95`): how alike two questions must be
  before one answer serves both. Lower it only with an evaluation set in front of you.
- `RESPONSE_CACHE_MAX_ENTRIES` (default `512`) / `RESPONSE_CACHE_TTL_SECONDS` (default
  `86400`, `0` meaning no expiry).
- `RESPONSE_CACHE_STORE_CONTEXT_FREE_ONLY` (default `true`): a correctness rule rather than a
  tuning knob — see the Response cache section above before changing it.

Optional — ingestion, monitoring and alerts:

- `INGEST_STALL_MINUTES` (default `15`): how long a document may sit in `processing` with no
  heartbeat before it is marked failed. Raise it for very large documents on slow hardware;
  the only cost of waiting is a row that reads `processing` for longer.
- `TELEMETRY_ENABLED` (default `true`), `TELEMETRY_SAMPLE_RATE` (default `1.0`). Off means no
  tracer, no writer, and no rows — the API behaves as it did before monitoring existed.
- `TELEMETRY_QUEUE_SIZE` / `TELEMETRY_BATCH_SIZE` / `TELEMETRY_FLUSH_INTERVAL_SECONDS` /
  `TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS`: the background writer's bounds.
- `TELEMETRY_CAPTURE_TEXT` (default `false`): allows instrumented stages to store raw question
  and answer text on their spans, where any admin can read it until retention removes it.
  Think before turning it on; the sanitiser strips credentials, not content.
- `TELEMETRY_RETENTION_DAYS` (default `30`) / `TELEMETRY_RETENTION_INTERVAL_HOURS` (default
  `24`): the retention sweep, which runs whether or not capture is enabled.
- `APP_ENV` / `APP_VERSION`: stamped onto every trace, so a regression can be attributed to a
  release and one environment's traffic told from another's.
- `ALERTS_ENABLED` (default `true`), and the thresholds `ALERT_ERROR_RATE`, `ALERT_P95_MS`,
  `ALERT_COST_PER_HOUR_USD`, `ALERT_DROPPED_RECORDS`, `ALERT_BM25_EMPTY_RATE`,
  `ALERT_MIN_REQUESTS`, `ALERT_INTERVAL_SECONDS`, `ALERT_WINDOW_MINUTES`, and
  `ALERT_WEBHOOK_URL`.
- `RUN_REAL_RAG_TESTS=1`: opts the integration test suites into hitting real Pinecone/Gemini.

Per-model daily token limits are deliberately not environment variables — they are constants
in `backend/wiring/rag_factory.py::_DAILY_TOKEN_LIMITS`, since they track what the provider
publishes rather than anything deployment-specific. Per-token prices are neither: they live in
the `model_pricing` table, so a price change is a new row with its own effective window rather
than a redeploy.

## Database And Migrations

Schema is managed with Alembic, twelve revisions from `0001_auth_tables` through
`0012_answer_feedback` — auth, conversations, documents, generation usage, telemetry and its
dimensions, span sequencing, token cost, the ingestion heartbeat, a span index, the error
taxonomy, and answer feedback. Apply them before starting the API for the first time:

```powershell
cd backend
alembic upgrade head
```

The models use portable SQLAlchemy types (`sa.Uuid`, `sa.JSON`, `String` + `CHECK` rather than
Postgres enums), which is why the whole backend test suite can run against a throwaway SQLite
file with no server required. Production and development both run against real PostgreSQL.

Two tables are populated by a script rather than by the app: `model_pricing` (see
`scripts/seed_model_pricing.py`, and read its header before running it) and `invite_codes`.
If you have an existing `storage/bm25_corpus.json` from before documents moved into Postgres,
`backend/scripts/migrate_bm25_corpus.py` imports it into the new tables.

## Running Ingestion

Ingestion is admin-only: `POST /api/ingest` (multipart PDF upload, requires an admin bearer
token) or the documents page in the frontend. Uploaded PDFs are written to
`backend/storage/uploads/`, ingested, and then deleted in a `finally` block. A PDF whose
content hash matches an already-`ready` document is rejected with 409 rather than duplicated.

`backend/scripts/run_ingestion.py` is a BM25 corpus verification script rather than a general
ingestion entry point — it chunks `backend/data/raw/cv.pdf` and asserts the records match the
chunks. Run it from the `backend/` directory:

```powershell
cd backend
python scripts\run_ingestion.py
```

## Running The API

Start the FastAPI app from the `backend/` directory, which is the runtime root for `.env`,
`data/`, and `storage/`:

```powershell
cd backend
uvicorn backend.app:app --reload
```

On startup the app verifies database connectivity, warns if the schema is behind the
migrations, seeds the administrator account if needed, reconciles any document left stuck
mid-ingest by a previous process, builds the RAG service (embedder, vector store, BM25 index,
reranker, response cache), and then starts the telemetry writer, the retention worker and the
alert evaluator. Telemetry is started last and guarded on both ends: the application must boot,
and must shut down, whether or not monitoring works.

Local URLs:

```text
API:  http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs
```

## Running The Frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

The app is served at `http://localhost:5173`. The Vite dev server proxies `/api` and
`/health` to `http://127.0.0.1:8000`, so no CORS configuration is needed in development. Point
it at a different backend by setting `VITE_BACKEND_URL`, either in `frontend/.env` or as a
shell variable. Build for production with `npm run build` (runs `tsc -b` first, so it also
type-checks).

The login screen lets you choose a light or dark theme, which is remembered per browser.
After signing in (or registering — with an optional invite code field), the app shows:

- a conversation sidebar (create, rename, delete), with the wordmark, API status, and account
  row pinned so only the conversation list scrolls
- a chat view with per-answer source citations — filename, page, chunk index, retrieval
  method, and score — behind a collapsible "N sources" disclosure
- a thumbs up/down control under each answer; pressing the thumb already showing withdraws the
  rating, and an optional note can be attached
- a model picker in the composer, listing whatever `GET /api/models` currently offers and
  remembering the last choice per browser (a custom dropdown rather than a native `<select>`,
  so the option list opens upward instead of being clipped at the bottom of the viewport)
- a "Sources" (`top_k`) control, visible to admins only

Admins get four more pages, with the dashboard as the landing page and the rest reachable from
it:

- `/admin/monitoring` — the dashboard, ordered by what makes you act rather than by data
  source. Band 1 is "is something wrong right now" (alerts, corpus health), band 2 "is it
  healthy" (requests, error rate, latency, in-flight), band 3 "is it behaving well and what
  does it cost" (stage latency, spend, retrieval and reranking behaviour, feedback, model
  usage). One time-range control at the top scopes everything, never per chart.
- `/admin/traces` and `/admin/traces/:traceId` — the trace explorer: filter by route, failure
  or conversation, then open one request as a span waterfall with its per-stage token and cost
  breakdown.
- `/admin/documents` — the library: upload, status, page/chunk counts, uploader, delete and
  purge.
- `/admin/users` — the roster: promote/demote, delete (deleting an admin requires typing their
  exact email).

The monitoring pages are code-split and lazily loaded: the charting library is around 400 kB,
they are admin-only and rarely opened, and students loading the chat should not pay for them.

## API Endpoints

Every route below is protected by dependency injection at `include_router()` time, so a new
route is protected by omission unless explicitly listed as public. See
`backend/tests/api/test_route_protection.py` for the enforced classification.

Every traced response carries `X-Trace-ID` and `X-Request-ID`, both exposed through CORS, so a
user can quote the id of a bad answer and an admin can open it in the trace explorer. An
inbound `X-Request-ID` is adopted if it looks like one and replaced otherwise. `/health` and
CORS preflights are not traced: the load balancer hits the former every few seconds, and
tracing it would bury real traffic and grow the tables for no insight.

### Health — public

```http
GET /health/health
```

### Authentication

```http
POST /api/auth/register     # public: open registration OR a valid invite code
POST /api/auth/login        # public
POST /api/auth/refresh      # public: rotates the httpOnly refresh cookie
POST /api/auth/logout       # public: acts on whatever refresh cookie is present
GET  /api/auth/me           # authenticated
POST /api/auth/logout-all   # authenticated: revokes every refresh token for the user
POST /api/auth/password     # authenticated: set/change password
```

Login and register both return an access token in the body and set an httpOnly,
`SameSite=Lax` refresh cookie scoped to `/api/auth`. Presenting an already-rotated refresh
token (a replay) revokes the entire token family, not just that one token.

Example:

```powershell
curl -X POST http://127.0.0.1:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"email\":\"admin@example.com\",\"password\":\"your-password\"}"
```

### Conversations — authenticated, scoped to the caller

```http
GET    /api/conversations
POST   /api/conversations
GET    /api/conversations/{id}
PATCH  /api/conversations/{id}
DELETE /api/conversations/{id}
```

A conversation belonging to another user returns 404, not 403, so the response cannot be used
to discover which conversation ids exist.

### Query — authenticated

```http
GET  /api/models            # generation models on offer, plus the server's default id
POST /api/query
```

`GET /api/models` lists only what is usable right now:

```json
{
  "models": [
    { "id": "gemini-flash", "label": "Gemini (default)", "provider": "gemini" },
    { "id": "groq-gpt-oss-120b", "label": "GPT-OSS 120B (Groq)", "provider": "groq" }
  ],
  "default": "gemini-flash"
}
```

Query request body. `model` is optional — omitted or `null` uses the default; an unknown or
unavailable id is a 400, never a silent substitution:

```json
{
  "conversation_id": "5b1f2e3a-2222-4444-8888-0123456789ab",
  "question": "Who is Nithusikan?",
  "top_k": 5,
  "model": "groq-gpt-oss-120b"
}
```

Requires a bearer token, e.g.:

```powershell
curl -X POST http://127.0.0.1:8000/api/query `
  -H "Authorization: Bearer <access_token>" `
  -H "Content-Type: application/json" `
  -d "{\"conversation_id\":\"5b1f2e3a-2222-4444-8888-0123456789ab\",\"question\":\"Who is Nithusikan?\",\"top_k\":5}"
```

If the conversation id doesn't exist yet it is created for the caller on first use, titled
from the question. Response shape:

```json
{
  "conversation_id": "5b1f2e3a-2222-4444-8888-0123456789ab",
  "question": "Who is Nithusikan?",
  "answer": "Generated answer from the retrieved document context.",
  "model": "groq-gpt-oss-120b",
  "processing_time_ms": 2140,
  "message_id": 417,
  "sources": [
    {
      "id": "cv.pdf_chunk_0",
      "score": 0.91,
      "retrieval_method": "rerank(hybrid)",
      "rerank_score": 0.87,
      "text": "Relevant source chunk text...",
      "preview": "Relevant source chunk text...",
      "metadata": {
        "document_id": "cv",
        "filename": "cv.pdf",
        "page_number": 1,
        "chunk_index": 0
      }
    }
  ]
}
```

`model` reports which model actually answered, and `message_id` is the stored id of the answer
so the client can rate it without reloading the conversation (`null` means rating is
unavailable rather than an error). The server-side upload path is deliberately absent from
`metadata` — the API schema drops it so a client is never handed the filesystem layout of the
server. Engine failures (Pinecone, Gemini, or Groq errors, which can carry credentials in their
message text) are logged server-side and returned to the client as a generic 502, never the raw
exception text.

### Feedback — authenticated

```http
POST   /api/feedback                      # {"message_id": 417, "rating": "up"|"down", "comment": "..."}
DELETE /api/feedback/{message_id}         # withdraw; idempotent
```

Rating an answer is the reader's own act, so these are authenticated rather than admin-only;
ownership is checked against the conversation, and someone else's message reads as 404. A
comment is optional and bounded — this is a rating with a note, not a second chat. Withdrawing
a rating that is not there succeeds: the caller wanted no rating to exist, and none does.

### Documents — admin-only

```http
POST   /api/ingest                        # multipart PDF upload
GET    /api/documents
DELETE /api/documents/{id}
POST   /api/documents/{id}/purge          # retry a failed deletion; sweeps orphan vectors
```

### Users — admin-only

```http
GET    /api/users
DELETE /api/users/{id}?confirm=true       # confirm=true required to delete another admin
PATCH  /api/users/{id}/role               # {"role": "admin"} or {"role": "user"}
```

An admin can never delete their own account, which is also what structurally guarantees a
delete can never drop the system to zero admins: the caller always survives. Demotion has no
such guarantee, so demoting the last remaining admin is rejected with 409.

### Usage — admin-only

```http
GET /api/usage/models
```

```json
{
  "models": [
    {
      "id": "groq-gpt-oss-120b",
      "label": "GPT-OSS 120B (Groq)",
      "provider": "groq",
      "daily_tokens_used": 18432,
      "daily_token_limit": 200000,
      "monthly_tokens_used": 204118,
      "monthly_token_limit": 6000000
    }
  ],
  "generated_at": "2026-09-16T09:30:00Z"
}
```

A `null` limit means the model has no configured quota — usage is still tracked, there is just
nothing to compare it against.

### Monitoring — admin-only

```http
GET /api/monitoring/overview       # requests, error count, slowest stages, spend, cache, in-flight
GET /api/monitoring/performance    # latency by stage, a bucketed series, counts by route
GET /api/monitoring/tokens         # tokens and estimated cost by model and by stage
GET /api/monitoring/retrieval      # retriever contribution, fusion, reranking depth
GET /api/monitoring/errors         # counts by category and by stage
GET /api/monitoring/ingestion      # ingestion stage timings plus knowledge-base health
GET /api/monitoring/feedback       # ratings, and the negative ones with their traces
GET /api/monitoring/alerts         # current rule states
GET /api/monitoring/traces         # ?limit&before&route&failed_only&conversation_id
GET /api/monitoring/traces/{id}    # one trace: span waterfall + per-stage tokens and cost
```

Monitoring exposes every user's traffic, conversation ids and spend, so it is admin-only in
its entirety — there is no per-user view of it.

Every endpoint but `/alerts` and `/traces/{id}` takes the same window parameters — `range` (one
of `15m`, `1h`, `6h`, `24h`, `7d`, `30d`) or an explicit `start`/`end` pair — and echoes the
resolved window back, so a chart can label itself without re-deriving what it asked for. Bucket
size for series data is chosen from the window rather than requested.

Two nulls are meaningful. `cache` is `null` when nothing was looked up, which is not a hit rate
of zero. `estimated_cost_usd` is `null` when the models involved have no pricing row, reported
alongside `pricing_configured` so the client says "not priced" rather than "$0.00".

## Terminal Scripts

All scripts live in `backend/scripts/` and are run from the `backend/` directory.

```powershell
cd backend

# Interactive conversational Q&A against the CV fixture
python scripts\ask_cv_from_terminal.py
python scripts\ask_cv_from_terminal.py "Who is the person in the CV?"

# Component smoke checks (real Pinecone/Gemini calls, not part of the test suite;
# named smoke_* rather than test_* so pytest never collects them by accident)
python scripts\smoke_rag.py
python scripts\smoke_retrieval.py
python scripts\smoke_reranker.py

# Retrieval quality against a labelled set; --save and --compare for experiments and drift
python scripts\evaluate_retrieval.py data\evaluation\example.json

# Fill model_pricing, without which cost reads "not priced" rather than zero.
# Read its header first: the rates shipped in it are placeholders.
python scripts\seed_model_pricing.py --dry-run

# BM25 corpus verification against backend/data/raw/cv.pdf
python scripts\run_ingestion.py

# One-time import of a legacy storage/bm25_corpus.json into Postgres
python scripts\migrate_bm25_corpus.py

# Destructive: drops and recreates the Pinecone index
python scripts\reset_pinecone.py
```

## Testing

Three kinds of suite, split by directory:

```powershell
# Engine — no external services (233 tests)
cd rag
python -m pytest tests\unit

# Backend unit + API — SQLite, no network; this is exactly what CI runs (549 tests)
cd backend
python -m pytest tests\unit tests\api

# Everything, including integration suites that skip themselves without
# RUN_REAL_RAG_TESTS=1
cd rag; python -m pytest
cd backend; python -m pytest
```

`backend/tests/conftest.py` builds a throwaway SQLite database per test and overrides
`get_db`, `get_auth_config`, and `get_rag_service` (stubbed) on the app; the `client` fixture
deliberately never enters the `TestClient` context manager, since that would run the real
lifespan and connect to the real database. The generation-model dependencies
(`GenerationModels`, `DefaultGenerationModelId`, `GeneratorResolver`) are reachable only
through `backend/dependencies.py` for the same reason — API tests override them with stubs
instead of needing real Gemini or Groq credentials.

`backend/tests/api/test_route_protection.py` compares a hand-written
public/authenticated/admin table against the routes the app actually exposes, so adding an
endpoint without deciding who may call it fails the build. Update that table in the same
commit as the route.

The aggregation, alerting, pricing, retention and knowledge-base modules are pure functions
over rows and thresholds, so their tests need neither HTTP nor a clock — which is why the
monitoring work is covered by unit tests rather than only by API ones.

Frontend type-check and build:

```powershell
cd frontend
npm run build
```

## Current Implementation Notes

- The FastAPI app is built in `backend.app:create_app` and registers ten routers: health,
  auth, conversations, ingest, documents, query, users, feedback, usage, and monitoring.
- `backend.wiring.rag_factory` builds the embedder, vector store, reranker, generator, BM25
  index, response cache, tracer and telemetry sink as cached singletons, and owns the
  generation-model catalog. Ingesting or deleting a document calls `refresh_corpus_state()`,
  which rebuilds the BM25 index in place and empties the response cache rather than tearing
  down the whole RAG service — the earlier design re-instantiated the embedder and reranker on
  every upload.
- `TelemetryMiddleware` is added before CORS so CORS ends up the outer of the two: a preflight
  is answered without ever reaching telemetry, and the browser can read the trace id because
  CORS exposes it explicitly.
- Pinecone indexes are created automatically with cosine similarity in AWS `us-east-1`.
- Embedding and reranking use Pinecone's hosted inference by default
  (`USE_HOSTED_INFERENCE=true`); local Sentence Transformer / cross-encoder models are a
  fallback behind the `local-models` extra. Heavy imports (`sentence-transformers`,
  `langchain-text-splitters`) happen inside constructors, not at module import.
- `BM25Index` is loaded from the `document_chunks` table via `backend/wiring/bm25_loader.py`,
  not from a JSON file, so it reflects the database rather than whatever a file on disk
  happened to contain. It is built from `ready` documents only, which is why the dashboard
  reports chunks stored and chunks retrievable as two separate numbers.
- Conversation memory is persisted in PostgreSQL per conversation and survives restarts.
- `top_k` is accepted by the query API (bounded 1..20); `candidate_k` defaults to `30` inside
  `HistoryAwareRAGService.answer_with_sources`.
- `POST /api/ingest` is a plain `def`, not `async def`, so FastAPI runs the fully synchronous,
  CPU-bound ingestion in a worker thread instead of blocking the event loop.
- `fastapi` is pinned rather than left open-ended: the route-classification test depends on
  how FastAPI exposes routes from included routers, and a major bump silently changed that.

## Known Limitations

- Text-based PDFs are supported; scanned PDFs need OCR before ingestion.
- There is no admin API for creating invite codes yet — insert a row into `invite_codes`
  directly, or run with `ALLOW_OPEN_REGISTRATION=true` for a small, trusted class.
- The response cache is per-process and in-memory: two uvicorn workers keep two caches, and a
  restart keeps none. A shared implementation would go behind the same `ResponseCache`
  protocol without the service changing.
- Cost figures are estimates from the `model_pricing` table, not provider invoices, and the
  rates shipped in `seed_model_pricing.py` are placeholders that must be checked against the
  providers' pricing pages before the table is seeded.
- Token usage is reported but not enforced: exhausting a model's daily quota fills the meter
  on the dashboard, it does not block queries or fail over to another model. Usage is
  aggregated per model, not per user.
- The Groq daily limits are hardcoded from Groq's published free-tier quotas and can drift if
  Groq changes them (the Qwen entry is the least certain of the three); the monthly ceiling is
  derived, not a real provider-side cap.
- Alerts are evaluated inside the API process and delivered by log line and optional webhook.
  With more than one instance running, each evaluates independently, so the same alert fires
  once per instance; there is no deduplication, escalation or acknowledgement.
- Telemetry is a single background thread behind a bounded queue: on a burst it drops records
  rather than slowing the request, so the numbers can be understated. The dropped count is
  reported, and is itself an alert rule.
- Offline evaluation ships with a template dataset and no labels. The metrics are real; the
  labelling is the expensive part, and until someone who knows the corpus writes it, the
  runner has nothing to score.
- Evaluation is retrieval-only. Answer quality needs a human or a judge model, which is
  deliberately out of scope — conflating the two would let a retrieval regression hide behind
  a well-written wrong answer.
- Google sign-in is deferred: `GOOGLE_CLIENT_ID` is read and an `oauth_accounts` table exists,
  but nothing in the API or frontend uses either yet.
- There is no password reset flow (no email provider is configured).
- No rate limiting on `/api/auth/login` or `/api/query`.
- Answers are returned whole rather than streamed, so a long generation shows a spinner for
  its full duration.
- Pinecone index name is not separated per environment, so a document deleted in a
  development deployment is also deleted in production if they share `PINECONE_INDEX_NAME`.
- No custom domain yet — the live deployment is reachable only via CloudFront's default
  `*.cloudfront.net` domain (deferred per `AWS_DEPLOYMENT_PLAN.md` section 1.11).
- API startup builds the embedder, vector store, BM25 index, and reranker clients, so cold
  start time depends on Pinecone/Gemini reachability even though no model weights are
  downloaded by default.
- No frontend test runner is configured; `npm run build` (via `tsc -b`) is the only automated
  frontend check.

## Useful Commands

```powershell
# Format
black rag\src rag\tests backend\src backend\tests

# Lint (includes a rule banning backend/fastapi/sqlalchemy imports inside rag/)
ruff check rag\src rag\tests backend\src backend\tests

# Apply database migrations
cd backend; alembic upgrade head

# Run API
cd backend; uvicorn backend.app:app --reload

# Run frontend
cd frontend; npm run dev

# Run engine unit tests
cd rag; python -m pytest tests\unit

# Run backend unit + API tests (what CI runs)
cd backend; python -m pytest tests\unit tests\api

# Retrieval quality against a labelled set
cd backend; python scripts\evaluate_retrieval.py data\evaluation\example.json
```

## Deployment

Live on AWS: ECS Fargate (backend container) + RDS (PostgreSQL) + S3/CloudFront (frontend, with
the same CloudFront distribution fronting the API so the two stay same-origin — required
because the refresh cookie is `SameSite=Lax`). Every AWS resource is still named with the
`medical-student-assistant` prefix the project was built under. Those names are load-bearing —
they appear in `backend-deploy.yml`, `task-definition.json` and the Secrets Manager ARNs — and
renaming them in the repository would point CI at resources that do not exist. Renaming them in
AWS means recreating the infrastructure, so the prefix stays; it is internal and no user sees
it. `AWS_DEPLOYMENT_PLAN.md` in the repository root
is the full runbook this deployment was built from — architecture decisions (read section 0
first), the one-time AWS setup, and the CI/CD design.

Deploys are automated via GitHub Actions on every push to `main`:

- **`.github/workflows/backend-deploy.yml`**: runs the engine + backend test suites, builds and
  pushes the Docker image to ECR, registers a new ECS task definition revision, runs
  `alembic upgrade head` as a one-off ECS task **against that exact revision** before touching
  the live service, and only then updates the ECS service — a failed migration stops the
  workflow before the service is ever pointed at code that expects a schema that isn't there
  yet. Triggers only on changes under `backend/`, `rag/`, or the `Dockerfile`.
- **`.github/workflows/frontend-deploy.yml`**: builds the frontend, syncs `dist/` to the S3
  bucket (`--delete`, so old fingerprinted bundles from previous builds don't pile up), and
  invalidates the CloudFront cache so visitors get the new build immediately rather than a
  stale cached one. Triggers only on changes under `frontend/`.
- **`backend/deploy/task-definition.json`**: the checked-in baseline task definition (roles,
  CPU/memory, port mapping, non-secret env vars, and references to the Secrets Manager secret
  for credentials) that the backend workflow renders a new image tag into on every run. Every
  provider key the app offers has to be listed here — a missing `GROQ_API_KEY` entry is why
  the deployed model picker once showed Gemini only while local development showed all four.

Both workflows authenticate to AWS via **OIDC** (a GitHub Actions-specific IAM role,
`medical-student-assistant-github-actions`, trusted only for pushes to `main` in this exact
repo) rather than long-lived access keys stored as secrets — the only repository secret
involved is `AWS_ROLE_ARN`.

Two things to do on a fresh deployment, neither of which the app does for you: run
`scripts/seed_model_pricing.py` with verified rates (otherwise cost reads "not priced"), and
decide `TELEMETRY_RETENTION_DAYS` before traffic starts, since the sweep only deletes what is
already past the window.

What's already in the repository and stays true regardless of host:

- **`Dockerfile`** (root): builds from the repo root since `backend` imports `rag`. No ML
  weights baked in — hosted inference means the image needs neither PyTorch nor
  sentence-transformers. Reads `$PORT` at runtime.
- **`.github/workflows/pr-checks.yml`**: on every PR — lint (ruff + black), engine tests,
  backend unit + API tests, a Docker build (not pushed), and a frontend build. Each job is
  skipped when its paths didn't change, and a skipped job still reports as a passing check, so
  branch protection stays satisfied. This workflow isn't tied to any deployment target.

## Recommended Next Improvements

1. Label a real evaluation set. Everything needed to measure retrieval quality is built; what
   is missing is questions paired with the chunks that genuinely answer them.
2. Enforce token limits rather than only reporting them — refuse or fail over when a model's
   daily quota is exhausted, and track usage per user as well as per model.
3. Move the response cache behind a shared store, so workers and restarts stop each keeping
   their own.
4. Add an admin API for creating, listing, and revoking invite codes.
5. Wire up Google sign-in (verify the ID token server-side, link by verified email).
6. Add a password reset flow once an email provider is available.
7. Add rate limiting on `/api/auth/login` and `/api/query`.
8. Separate Pinecone indexes per environment.
9. Stream answers to the frontend instead of waiting for the full generation.
10. Add frontend tests (no runner is configured yet).

## Future Direction: Structure-Aware Chunking (Proposed)

The current chunker splits recursively by character count with a fixed overlap; each chunk's
metadata already carries a `section_title` and `heading_level`, but there is no chapter/section
hierarchy resolver or parent-child chunk relationship behind them yet. The diagram below is a
proposed pipeline for structure-aware ingestion — parsing headings, lists, tables, and figures
as first-class elements, building a document hierarchy, and generating parent/child chunks
that inherit their heading path — kept here as a design reference, not a description of what
is implemented today.

```text
Ingestion Pipeline (proposed)

                                   ┌────────────────────┐
                                   │   PDF Document     │
                                   │ (Medical Textbook) │
                                   └─────────┬──────────┘
                                             │
                                             ▼
                             ┌────────────────────────────────┐
                             │        1. Parser               │
                             │--------------------------------│
                             │ • Extract text                 │
                             │ • Extract headings             │
                             │ • Extract lists                │
                             │ • Extract tables               │
                             │ • Extract figures              │
                             │ • Preserve reading order       │
                             │ • Preserve parent IDs          │
                             │ • Preserve page numbers        │
                             └──────────────┬─────────────────┘
                                            │
                                            ▼
                                     ParsedDocument
                                            │
                                            ▼
                          ┌────────────────────────────────────────┐
                          │      2. Structure Resolver             │
                          │----------------------------------------│
                          │ Build semantic document hierarchy      │
                          │                                        │
                          │ Chapter                                │
                          │   └── Section                          │
                          │         └── Subsection                 │
                          │               └── Elements             │
                          │                                        │
                          │ Generate heading paths                 │
                          │ Resolve parent references              │
                          └──────────────┬─────────────────────────┘
                                         │ 
                                         ▼
                                  StructuredDocument
                                         │
                                         ▼
                 ┌────────────────────────────────────────────┐
                 │        3. Semantic Chunk Builder           │
                 │--------------------------------------------│
                 │ Build logical blocks instead of            │
                 │ fixed-size chunks                          │
                 │                                            │
                 │ • Heading + paragraphs                     │
                 │ • Entire lists                             │
                 │ • Entire tables                            │
                 │ • Figure + caption                         │
                 │ • Algorithm + steps                        │
                 └──────────────┬─────────────────────────────┘
                                │
                                ▼
                        Semantic Blocks
                                │
                                ▼
        ┌──────────────────────────────────────────────────────────┐
        │          4. Parent-Child Chunk Generator                 │
        │----------------------------------------------------------│
        │ If block is small                                        │
        │      → one chunk                                         │
        │                                                          │
        │ If block is large                                        │
        │      → Parent chunk                                      │
        │      → Child chunks                                      │
        │                                                          │
        │ Every child inherits                                     │
        │ Chapter                                                  │
        │ Section                                                  │
        │ Heading Path                                             │
        └──────────────┬───────────────────────────────────────────┘
                       │
                       ▼
               Context-aware Chunks
                       │
                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │          5. Chunk Enrichment                             │
        │----------------------------------------------------------│
        │ Add retrieval metadata                                   │
        │                                                          │
        │ • chunk_id                                               │
        │ • parent_chunk_id                                        │
        │ • document_id                                            │
        │ • heading_path                                           │
        │ • page_start/end                                         │
        │ • element_ids                                            │
        │ • parser                                                 │
        │ • source_ids                                             │
        └──────────────┬───────────────────────────────────────────┘
                       │
                       ▼
                Enriched Chunks
                       │
                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │           6. Embedding Generator                         │
        │----------------------------------------------------------│
        │ Embed ONLY                                               │
        │                                                          │
        │ chunk.text                                               │
        │                                                          │
        │ Metadata is NOT embedded                                 │
        └──────────────┬───────────────────────────────────────────┘
                       │
                       ▼
                  Embedding Vector
                       │
                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │           7. Vector Store Builder                        │
        │----------------------------------------------------------│
        │ Build final vector record                                │
        │                                                          │
        │ {                                                        │
        │   id                                                     │
        │   embedding                                              │
        │   text                                                   │
        │   metadata                                               │
        │ }                                                        │
        └──────────────┬───────────────────────────────────────────┘
                       │
                       ▼
                    Pinecone
```
