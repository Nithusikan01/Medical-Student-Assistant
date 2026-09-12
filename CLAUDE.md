# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A full-stack RAG (Retrieval-Augmented Generation) application for a class of students: an
admin uploads and manages a shared PDF library, and any registered user asks questions against
it. It extracts text from PDFs, chunks it, embeds it (Pinecone hosted inference by default,
local Sentence Transformers as a fallback), stores/retrieves vectors in Pinecone, fuses dense
retrieval with BM25 lexical retrieval, reranks (also Pinecone hosted by default), and generates
answers with Google Gemini. Conversation memory is persisted per user in PostgreSQL and lets
follow-up questions get rewritten into standalone retrieval queries. Auth is JWT access tokens
plus rotating httpOnly-cookie refresh tokens with reuse detection. A React + TypeScript
frontend provides login/register, chat, and (admin-only) document management.

## Repository layout

Three top-level parts, two of them installable Python packages:

- `rag/` — the RAG engine, package `rag`. Pure library: no FastAPI, no HTTP, no database.
  Contains `config/`, `conversation/` (memory + the `ConversationStore` protocol),
  `embeddings/`, `evaluation/`, `indexes/`, `ingestion/` (including the `ChunkSink` protocol),
  `llm/`, `retrieval/`, `services/`, `utils/`, `vectorstore/`, plus its own `tests/`.
- `backend/` — the FastAPI layer, package `backend`. Contains `app.py`, `dependencies.py`,
  `auth/` (password hashing, JWT/refresh tokens, `AuthService`), `db/` (SQLAlchemy models and
  repositories), `migrations/` (Alembic), `schemas/`, `routers/`, `services/` (upload handling,
  document lifecycle, the Postgres-backed conversation store), and `wiring/rag_factory.py` (the
  composition root). Also holds `scripts/`, `.env`, `data/`, and `storage/`.
- `frontend/` — Vite + React + TypeScript web app.

`backend` depends on `rag`; `rag` must never import `backend`, `fastapi`, or `sqlalchemy` — a
ruff `TID251` rule (`flake8-tidy-imports.banned-api` in `rag/pyproject.toml`) enforces this at
lint time. `backend/` is the runtime root: `.env`, `data/raw/`, and `storage/` are resolved
relative to it, so run uvicorn, Alembic, and the scripts from inside `backend/`. Where the
engine needs persistence, it depends on a protocol defined in `rag/` (`ConversationStore`,
`ChunkSink`) whose database-backed implementation lives in `backend/`.

## Commands

Install (editable, with dev deps) — `rag` first, since `backend` imports it:

```powershell
python -m pip install -e "./rag[dev]"
python -m pip install -e "./backend[dev]"
cd frontend; npm install
```

Run tests (each package owns its suite; `pythonpath` is configured in each `pyproject.toml`, so no install is strictly needed):

```powershell
cd rag; python -m pytest tests\unit                  # engine, no external services
cd backend; python -m pytest                         # all three suites below
cd backend; python -m pytest tests\unit tests\api    # exactly what CI runs
cd rag; python -m pytest tests\unit\test_pipeline.py::test_ingestion_pipeline_runs_all_steps
```

Three kinds of suite, split by directory because that is what CI selects on:

- `rag/tests/unit/` and `backend/tests/unit/` — no HTTP, no external services. The backend ones still use a database: a throwaway SQLite file per test, built by `backend/tests/conftest.py`.
- `backend/tests/api/` — through `TestClient` against the real app, with `get_db`, `get_auth_config`, and `get_rag_service` overridden. The `client` fixture deliberately does *not* enter the TestClient context manager, because that would run the lifespan and connect to the real database.
- `rag/tests/integration/` and `backend/tests/integration/` — the only suites that touch Pinecone/Gemini or download model weights. They `pytest.skip()` at module level unless `RUN_REAL_RAG_TESTS=1`, so a green run does **not** mean credentials are configured.

`backend/tests/api/test_route_protection.py` compares a hand-written classification table against the routes the app actually exposes, so adding an endpoint without deciding who may call it fails the build. Update that table in the same commit as the route.

The backend fixtures work because the models use portable types (`sa.Uuid`, `sa.JSON`, `String` + `CHECK` rather than PG enums); `conftest.py` additionally patches the SQLite dialect to return timezone-aware datetimes, so expiry comparisons behave as they do on Postgres.

Format and lint:

```powershell
black rag\src rag\tests backend\src backend\tests
ruff check rag\src rag\tests backend\src backend\tests
```

Run the API and the frontend (two terminals):

```powershell
cd backend; uvicorn backend.app:app --reload
cd frontend; npm run dev
```

The Vite dev server (port 5173) proxies `/api` and `/health` to `http://127.0.0.1:8000`; override with `VITE_BACKEND_URL` in `frontend/.env` or the shell (`vite.config.ts` reads it via `loadEnv`, so both work). `npm run build` runs `tsc -b` first, so it also type-checks.

Ingestion runs through `POST /api/ingest` (multipart upload) or the frontend's upload panel — there is no CLI ingestion entry point (`main.py` was deleted). Ad-hoc scripts in `backend/scripts/` are for manual smoke testing, not part of the test suite: `ask_cv_from_terminal.py` (interactive Q&A), `smoke_rag.py` / `smoke_retrieval.py` / `smoke_reranker.py` (component smoke checks — named `smoke_` rather than `test_` so pytest cannot collect them), `run_ingestion.py` (BM25 corpus verification, despite the name), `migrate_bm25_corpus.py` (imports a legacy `bm25_corpus.json` into the database), `reset_pinecone.py` (drops and recreates the Pinecone index — destructive).

Required environment variables (`.env` in `backend/`, templated by `backend/.env.example`): `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `GEMINI_API_KEY`, `DATABASE_URL` (PostgreSQL), `SECRET_KEY` (JWT signing, ≥32 chars), `ADMIN_EMAIL`/`ADMIN_PASSWORD` (seeded on startup, idempotent — an existing password is never overwritten). Retrieval/chunking/embedding variables (`CHUNK_SIZE`, `CANDIDATE_K`, `USE_HOSTED_INFERENCE`, etc.) are read in `rag/src/rag/config/settings.py::load_settings`; auth/database variables (`ALLOW_OPEN_REGISTRATION`, `COOKIE_SECURE`, `CORS_ORIGINS`, token TTLs) are read in `backend/src/backend/auth/config.py::load_auth_config` and `backend/src/backend/app.py::cors_origins`. `.env` files are gitignored at any depth; `.env.example` files are committed. Apply migrations before first run: `cd backend; alembic upgrade head` (three revisions: `0001_auth_tables`, `0002_conversations`, `0003_documents`).

## Architecture

### Auth and authorization

JWT access tokens (HS256, 15 min default) plus opaque refresh tokens stored only as a sha256
hash (`backend/auth/tokens.py`), rotated on every `/api/auth/refresh` call
(`AuthService.rotate_refresh_token`). Presenting an already-rotated token means it leaked — the
whole `family_id` is revoked, not just that token. Passwords are hashed with `bcrypt` directly
(not passlib — 4.x bcrypt breaks passlib's version probe), and a malformed stored hash fails
closed via `_looks_like_bcrypt` rather than reaching `bcrypt.checkpw`, which panics on the
Rust side for a truncated digest. A failed login burns the same amount of time as a real
comparison (`burn_password_comparison`) so a missing account and a wrong password are
indistinguishable.

Endpoint protection is applied at `include_router(dependencies=[...])` level in `app.py`, not
per-route decorators, so a new router is protected by omission rather than by remembering to
add a check. `backend/tests/api/test_route_protection.py` encodes the intended
public/authenticated/admin classification as data and fails the build if a route doesn't match
it — update that table in the same commit as a new route. A conversation or document owned by
someone else returns 404, never 403, so the response can't be used to enumerate ids.

### Two independent pipelines, one wiring point

Everything is assembled through dependency injection, not framework magic. The two pipelines share components (`Embedder`, `PineconeVectorStore`) but are built separately:

- **Ingestion** (`rag/ingestion/pipeline.py::IngestionPipeline.ingest`) is constructed per-request in `backend/routers/ingest.py::get_ingestion_pipeline()`, and driven by `backend/services/document_service.py::DocumentService.ingest`, which creates the `documents` row (`status=processing`) *before* the pipeline runs.
- **Query** (`rag/services/history_aware_rag_service.py::HistoryAwareRAGService`) is built once by `backend/wiring/rag_factory.py::build_history_aware_rag_service()` — an `@lru_cache()`d factory called at API startup (`backend/app.py` lifespan).

`rag_factory.py` also exposes `build_embedder()`, `build_reranker()`, `build_vector_store()`, and `build_bm25_index()` as their own `@lru_cache()`d singletons. Ingesting or deleting a document calls `refresh_bm25_index()`, which reloads chunks from Postgres and calls `.rebuild()` on the *same* `BM25Index` object — the running `HistoryAwareRAGService` holds a reference to it and sees the change immediately. This replaced an earlier design that called `build_history_aware_rag_service.cache_clear()` on every ingest, which re-instantiated the embedder and reranker (and, before hosted inference, reloaded model weights) on every single upload.

When changing how a component is constructed (e.g. adding a retriever, changing model names), `rag_factory.py` is the single place that wires it into the live query path. It lives in `backend/` because it is application composition, not library code — the `rag` package deliberately ships no composition root.

### Ingestion path

```
PDF file -> DocumentLoader -> TextChunker -> Embedder -> VectorDataProcessor -> PineconeVectorStore
                                    |
                                    +--> ChunkSink -> document_chunks table (Postgres)
```

`IngestionPipeline.ingest()` batches chunks (`batch_size`) and, for each batch, upserts to Pinecone *and* writes to the chunk sink in the same loop — both incrementally per document. `ChunkSink` (`rag/ingestion/sinks.py`) is a Protocol; `backend/services/postgres_chunk_sink.py::PostgresChunkSink` is the production implementation, writing rows whose `id` is exactly the Pinecone vector id (`{document_id}_chunk_{i}`) — that table is simultaneously the BM25 text source and the authoritative list of vector ids for deletion. The engine's own file-based `BM25CorpusBuilder` (`ingestion/bm25/corpus_builder.py`) still exists and still satisfies `ChunkSink` structurally, so `rag/` remains usable with no database; it's just not what production wires up (see `backend/scripts/migrate_bm25_corpus.py` for importing an old `bm25_corpus.json`).

### Query path

```
conversation_id + question
  -> PersistentConversationMemory (Postgres-backed, per conversation, hydrated on each build)
  -> QueryRewriter (LLM call: folds conversation history into a standalone query)
  -> HybridRetriever
       -> DenseRetriever -> PineconeVectorStore
       -> BM25Retriever  -> BM25Index (loaded from document_chunks at factory build time, refreshed in place after ingest/delete)
       (fused via Reciprocal Rank Fusion, see hybrid_retriever.py)
  -> Reranker (Pinecone hosted by default, local cross-encoder as a fallback)
  -> PromptBuilder -> GeminiGenerator
  -> answer + structured RetrievedChunk sources
  -> ConversationMemory updated; summarized once message count hits HistoryAwareRAGService.SUMMARY_TRIGGER
```

`backend/services/conversation_store.py::PersistentConversationMemory` subclasses the engine's `ConversationMemory` and write-throughs every message to Postgres. It deliberately tracks two separate views: `messages` holds only turns since the last summary checkpoint (`Conversation.summary_checkpoint_message_id`) — this is what `HistoryAwareRAGService` checks against `SUMMARY_TRIGGER` — while `_recent` is a fixed-size window over the *full* history and is what actually goes into the prompt. Hydrating full history into `messages` too would make the trigger condition permanently true past the trigger length and fire an extra Gemini call every turn, forever; `update_summary` advances the checkpoint and clears `messages` back to empty.

`session_manager` in `HistoryAwareRAGService`'s constructor is typed against `rag/conversation/store.py::ConversationStore` (a Protocol with one method, `get_memory()`); the engine's own in-process `SessionManager` satisfies it structurally and is still what the unit tests use, but `backend/services/conversation_store.py::PersistentConversationStore` is what production wires up. Not one line of `SessionManager` changed to make this work — that's the point of the protocol seam.

### Document deletion ordering

`backend/services/document_service.py::DocumentService.delete` has to run in a specific order: mark `status='deleting'` (committed immediately) → `refresh_bm25_index()` (lexical retrieval stops seeing the document now) → delete Pinecone vectors in batches of ≤1000 (Pinecone's per-call cap) → delete the `documents` row (cascades to `document_chunks`). BM25 first, deliberately, so a document is never "delisted but still retrievable" during the window between the two removals. A failed vector delete raises `DocumentDeletionError` (message masked — the underlying exception can carry a Pinecone key) and leaves the row in `deleting`; `POST /api/documents/{id}/purge` retries and additionally sweeps vector ids sharing the document's id prefix with no matching chunk row, since Pinecone's serverless tier has no delete-by-metadata-filter and `list_ids()` is only safe to use for this kind of admin-triggered reconciliation, not the primary delete path.

### Data model chain (why there are five near-identical "chunk" types)

Each ingestion/retrieval stage has its own dataclass rather than one mutable object threaded through, so trace metadata by stage:

All under `rag/src/rag/` unless noted:

1. `ingestion/schemas.py`: `LoadedPage`/`LoadedDocument` (raw text) -> `ChunkMetadata`/`DocumentChunk` (post-chunking) -> `EmbeddedChunk` (adds `embedding`).
2. `vectorstore/schemas.py`: `VectorRecord`/`VectorRecordMetadata` (what's sent to Pinecone — `to_dict()` drops `None` fields because Pinecone rejects null metadata values) and `SearchResult` (what comes back from a query).
3. `retrieval/schemas.py`: `RetrievedChunk`/`RetrievedChunkMetadata` (post-retrieval/rerank, carries `dense_score`/`bm25_score`/`hybrid_score`/`rerank_score`/`retrieval_method`).

`ChunkMetadata` is the canonical field set (document_id, filename, source_path, page_number, section_title, heading_level, start_char/end_char, chunk_size, overlap_size, element_id/type, language, tags); the other metadata dataclasses mirror it for their stage. When adding a metadata field, it typically needs updating in all three places plus `BM25Metadata` (`ingestion/bm25/schemas.py`), the API's `SourceMetadata` (`backend/src/backend/schemas/query.py` — note `source_path` is deliberately dropped there, since it's the server's absolute upload path), and the mirrored TypeScript interface in `frontend/src/types.ts`.

### Config

`config/settings.py::Settings` is a frozen dataclass populated from env vars by `load_settings()`; component-specific config is carved out via `Settings.<x>_config()` methods returning the small dataclasses in `config/component_configs.py` (`EmbeddingConfig`, `ChunkingConfig`, `GenerationConfig`, `PineconeConfig`, `RetrievalConfig`). Components take their narrow config dataclass in `__init__`, not the whole `Settings` object — follow that pattern for new components.

### Heavy imports are lazy

`sentence-transformers` (`Embedder`, `Reranker`, `DenseRetriever`) and `langchain-text-splitters` (`TextChunker`) are imported inside constructors/builders, not at module top level, so importing these modules doesn't force a slow ML-library load for code paths that don't need it (e.g. API startup before the factory runs, or CLI scripts that only touch schemas).

### API surface

Six routers under `/api` (plus `/health`), mounted in `app.py::create_app`: `auth` (register/login/refresh/logout/logout-all/me/password — see Auth above), `conversations` (CRUD, ownership-checked), `ingest` (`POST /api/ingest`, admin-only, multipart PDF upload via `backend/services/upload_service.py`, which saves to `backend/storage/uploads/` and deletes it in a `finally` block), `documents` (admin-only list/delete/purge), and `query` (`POST /api/query`, any authenticated user, depends on `app.state.rag_service` via `backend/dependencies.py::get_rag_service`). Query `top_k` is bounded `1..20` via a pydantic `Field` constraint in `backend/schemas/query.py`. `POST /api/ingest` is a plain `def`, not `async def`, so FastAPI runs the fully synchronous, CPU-bound ingestion in a worker thread instead of blocking the event loop for every other request. Health is `GET /health/health` (the router is mounted under a `/health` prefix and declares `/health` itself).

### Frontend

Vite + React 18 + TypeScript, no UI framework — plain hooks, `react-router-dom` for routing, and one CSS file (`src/index.css`) with light/dark theme via CSS custom properties (`src/theme/ThemeContext.tsx`, chosen on the login screen, persisted in `localStorage`). `src/auth/AuthContext.tsx` holds the access token in memory (never `localStorage`) and does a silent refresh on mount to restore the session; `src/api/client.ts` attaches the bearer token and does a single-flight 401 refresh — a module-level promise so concurrent 401s trigger one refresh call, not one per request. Routes are gated by `src/components/RouteGuards.tsx` (`ProtectedRoute`, `AdminRoute`, both showing a boot spinner until the silent refresh resolves). `src/api/client.ts` uses relative URLs (`/api/...`, `/health/health`) so the Vite proxy handles dev routing and no base URL is baked into the bundle. In production the frontend and API must still share one origin — the refresh cookie is `SameSite=Lax`, which is not sent on a cross-site `fetch` — so whatever fronts the deployed app (a CDN behavior, a reverse proxy) has to route `/api/*` and `/health*` to the backend rather than calling it cross-origin; see `AWS_DEPLOYMENT_PLAN.md` section 0.1 for the current deployment target's approach (a CloudFront behavior in front of the ALB). `src/types.ts` mirrors the pydantic response models by hand — keep it in sync when API schemas change. `useConversation` takes the conversation id from the route (`/c/:conversationId`) rather than always minting a new UUID, so reloading a conversation replays its persisted messages and sources. Backend CORS is controlled by `CORS_ORIGINS` and already allows `localhost:5173` by default for running the frontend without the proxy.
