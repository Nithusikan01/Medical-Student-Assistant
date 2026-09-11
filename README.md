# RAG Application

A full-stack Retrieval Augmented Generation application for a class of students to ask
questions against a shared library of documents: a Python RAG engine, a FastAPI backend with
JWT authentication and PostgreSQL persistence, and a React + TypeScript web app. An admin
uploads and manages the PDF library; every signed-in user asks questions against it, with
their own private, resumable conversation history.

Retrieval is hybrid (dense + BM25, fused with Reciprocal Rank Fusion) and reranked; both
embedding and reranking run on Pinecone's hosted inference by default, so the deployed API
needs no PyTorch and downloads no model weights. Answers come from Google Gemini.
Conversation-aware query rewriting lets follow-up questions get folded into standalone
retrieval queries, and a rolling summary keeps long chats bounded.

## Current Capabilities

- Email/password registration and login with JWT access tokens and rotating, httpOnly-cookie
  refresh tokens (reuse detection revokes the whole token family)
- Two roles: `admin` (uploads and manages the shared document library) and `user` (asks
  questions, manages only their own conversations)
- Registration gated by an open-registration flag or an invite code, either is sufficient
- The first admin is seeded from environment variables on startup, idempotently
- PostgreSQL persistence via SQLAlchemy 2.0 and Alembic: users, refresh tokens, invite codes,
  conversations and messages, and the document/chunk registry
- Conversations are private, persisted, and resumable across restarts and devices, with a
  checkpointed rolling summary so long chats don't re-summarize on every turn
- PDF text extraction with `pypdf`, recursive chunking with LangChain text splitters
- Dense embeddings and reranking through Pinecone's hosted inference
  (`llama-text-embed-v2` / `bge-reranker-v2-m3` by default), with local Sentence Transformer /
  cross-encoder models available as a fallback
- BM25 lexical retrieval with `rank-bm25`, sourced from the same Postgres chunk table that
  backs Pinecone, so ingesting or deleting a document updates both retrieval paths together
- Hybrid retrieval via Reciprocal Rank Fusion across dense and BM25 results
- Gemini generation through `google-genai` with retry handling
- Document lifecycle: admin-only upload (deduplicated by content hash), listing, deletion
  (BM25 refreshed before vectors are removed, so a document is never "delisted but still
  retrievable"), and an orphan-sweep purge endpoint for a delete that failed partway
- FastAPI health, auth, conversation, document, and query endpoints, every one of them
  deliberately classified as public, authenticated, or admin-only and enforced accordingly
- React + TypeScript web app: light/dark theme (chosen on the login screen, persisted per
  browser), login/register screens, a conversation sidebar, per-answer source inspection, and
  an admin-only document management screen
- Docker image and GitHub Actions CI/CD (lint, tests, image build, migration-then-deploy)
- 260+ tests across the engine and backend, all hermetic (SQLite, no network)

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
list of Pinecone vector ids for that document. The document is flipped to `ready` and the
in-memory BM25 index is rebuilt in place once ingestion finishes.

The query path (`POST /api/query`, any signed-in user):

```text
conversation_id + question
  -> PersistentConversationMemory (Postgres-backed, per conversation)
  -> QueryRewriter (LLM call: folds conversation history into a standalone query)
  -> HybridRetriever
       -> DenseRetriever -> Pinecone
       -> BM25Retriever  -> BM25Index (built from document_chunks)
       (fused via Reciprocal Rank Fusion)
  -> Reranker (Pinecone hosted, or local cross-encoder)
  -> PromptBuilder -> GeminiGenerator
  -> answer + structured sources
  -> messages persisted; summarized once the trigger is reached
```

Conversation memory is deliberately split into two views: `messages` holds only the turns
since the last summary checkpoint (this is what drives the summarization trigger), while a
separate `_recent` window drives what actually goes into the prompt. Naively hydrating full
history into both would make the trigger permanently true past a dozen or so messages and
fire an extra Gemini call on every turn, forever.

Document deletion runs in a specific order for the same reason: BM25 is refreshed first
(lexical retrieval stops seeing the document immediately), *then* Pinecone vectors are
deleted in batches of at most 1000 (Pinecone's per-call cap), and only then is the registry
row removed. A failed vector delete leaves the row in a `deleting` state that an admin can
retry via `POST /api/documents/{id}/purge`, which also sweeps any vector ids that share the
document's id prefix but have no matching chunk row (Pinecone's serverless tier does not
support delete-by-metadata-filter, so this sweep — not a filtered delete — is the recovery
path).

## Project Structure

The repository is a monorepo with three top-level parts, two of them installable Python
packages:

```text
Medical-Student-Assistant/
|-- rag/                          # RAG engine (importable library, no HTTP, no database)
|   |-- pyproject.toml            # package: rag
|   |-- src/rag/
|   |   |-- config/               # Settings + per-component config dataclasses
|   |   |-- conversation/         # ConversationMemory, ConversationStore protocol,
|   |   |                         # query rewriting, summarization
|   |   |-- embeddings/           # PineconeEmbedder (hosted) + TextEmbedder protocol
|   |   |-- indexes/              # BM25Index (in-place .rebuild())
|   |   |-- ingestion/            # loader, chunker, embedder, pipeline, ChunkSink protocol
|   |   |-- llm/                  # Gemini generator + prompt builder
|   |   |-- retrieval/            # dense, bm25, hybrid, reranker (local + Pinecone hosted)
|   |   |-- services/             # HistoryAwareRAGService
|   |   |-- utils/
|   |   `-- vectorstore/          # Pinecone store
|   `-- tests/
|       |-- fixtures/
|       |-- integration/          # touches real Pinecone/Gemini; skips without an env flag
|       `-- unit/                 # no external services
|-- backend/                      # FastAPI HTTP layer (runtime root)
|   |-- pyproject.toml            # package: backend
|   |-- .env                      # credentials live here
|   |-- alembic.ini, migrations/  # 3 revisions: auth tables, conversations, documents
|   |-- data/raw/                 # source PDFs
|   |-- storage/                  # uploads/ (deleted after ingestion)
|   |-- scripts/                  # ad-hoc smoke-test / maintenance scripts
|   |-- src/backend/
|   |   |-- app.py                # create_app + lifespan (db connectivity, admin seeding)
|   |   |-- dependencies.py       # get_current_user, require_admin, DB session, etc.
|   |   |-- auth/                 # password hashing, JWT + refresh tokens, AuthService
|   |   |-- db/                   # SQLAlchemy models and repositories
|   |   |-- routers/              # health, auth, conversations, ingest, documents, query
|   |   |-- schemas/              # request/response models
|   |   |-- services/             # upload handling, document lifecycle, conversation store
|   |   `-- wiring/               # rag_factory: builds the live RAG service and BM25 index
|   `-- tests/
|       |-- unit/                 # SQLite, no HTTP
|       |-- api/                  # through TestClient against the real app
|       `-- integration/          # touches real Pinecone/Gemini; skips without an env flag
`-- frontend/                     # React + TypeScript (Vite) web app
    |-- package.json
    |-- vite.config.ts            # proxies /api and /health to the backend
    |-- vercel.json               # production rewrites to the deployed backend
    `-- src/
        |-- api/                  # typed fetch client (client, auth, conversations, documents)
        |-- auth/                 # AuthContext, useAuth, single-flight token refresh
        |-- theme/                # ThemeContext, useTheme (light/dark, persisted)
        |-- components/           # ChatPanel, ConversationSidebar, SourceList,
        |                         # RouteGuards (Protected/Admin), ThemeToggle, Icons
        |-- pages/                # LoginPage, RegisterPage, ChatPage, AdminDocumentsPage
        `-- hooks/                # useConversation
```

`backend` depends on `rag`; `rag` never imports `backend`, `fastapi`, or `sqlalchemy` — a
ruff `TID251` rule enforces this at lint time. `backend/` is the runtime root: `.env`,
`data/raw/`, and `storage/` are resolved relative to it, so run uvicorn, Alembic, and the
scripts from inside `backend/`. Where the engine needs persistence (conversation memory, the
BM25 corpus), it depends on a protocol defined in `rag/` (`ConversationStore`, `ChunkSink`)
whose database-backed implementation lives in `backend/`.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer (for the frontend)
- A PostgreSQL database (a free-tier hosted instance such as Supabase works)
- Pinecone API key and index name
- Google Gemini API key
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

`backend/.env.example` documents every variable with its default. The frontend has its own
optional `frontend/.env.example`, whose only knob is `VITE_BACKEND_URL`. Both `.env` files are
gitignored; the `.env.example` files are committed.

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
- `GEMINI_API_KEY`: Google Gemini API key.
- `DATABASE_URL`: a PostgreSQL connection string, `postgresql+psycopg://...`.
- `SECRET_KEY`: signs access tokens. At least 32 characters; treat it like a password, since
  changing it invalidates every issued access token. Use a different value in production than
  in local development.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD`: the first administrator, seeded on startup if no user with
  that email exists yet. An existing account's password is never overwritten by this, so
  rotating the live admin password does not get silently reset on the next deploy.
  `ADMIN_PASSWORD` must be at least 12 characters or seeding is skipped (logged as an error).

Optional variables (see `backend/.env.example` for the complete, commented list):

- `ALLOW_OPEN_REGISTRATION` (default `false`): when false, `POST /api/auth/register` requires
  a valid invite code. There is currently no admin API for creating invite codes — insert a
  row into the `invite_codes` table directly, or leave open registration on for a small,
  trusted class.
- `CORS_ORIGINS`: comma-separated allowed origins for the deployed frontend. Falls back to
  `http://localhost:5173` / `http://127.0.0.1:5173` for local development.
- `COOKIE_SECURE` (default `false`): set to `true` wherever the app is served over HTTPS, so
  the refresh cookie only travels encrypted. Leave `false` for local HTTP development.
- `ACCESS_TOKEN_TTL_MINUTES` (default `15`), `REFRESH_TOKEN_TTL_DAYS` (default `30`).
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
- `GENERATION_MODEL_NAME` (default `gemini-3.1-flash-lite`).
- `GOOGLE_CLIENT_ID`: reserved for a future Google sign-in; not currently wired up (see
  Known Limitations).
- `RUN_REAL_RAG_TESTS=1`: opts the integration test suites into hitting real Pinecone/Gemini.

## Database And Migrations

Schema is managed with Alembic, three revisions: `0001_auth_tables`, `0002_conversations`,
`0003_documents`. Apply them before starting the API for the first time:

```powershell
cd backend
alembic upgrade head
```

The models use portable SQLAlchemy types (`sa.Uuid`, `sa.JSON`, `String` + `CHECK` rather than
Postgres enums), which is why the whole backend test suite can run against a throwaway SQLite
file with no server required. Production and development both run against real PostgreSQL.

If you have an existing `storage/bm25_corpus.json` from before documents moved into Postgres,
`backend/scripts/migrate_bm25_corpus.py` imports it into the new tables.

## Running Ingestion

Ingestion is admin-only: `POST /api/ingest` (multipart PDF upload, requires an admin bearer
token) or the admin document management screen in the frontend. Uploaded PDFs are written to
`backend/storage/uploads/`, ingested, and then deleted. A PDF whose content hash matches an
already-`ready` document is rejected with 409 rather than duplicated.

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

On startup the app verifies database connectivity, seeds the administrator account if
needed, and builds the RAG service (embedder, vector store, BM25 index, reranker).

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
After signing in (or registering — with an optional invite code field), the app shows a
conversation sidebar, a chat view with per-answer source citations (filename, page, chunk
index, retrieval method, and score), and a `top_k` control. Admins additionally see a document
management screen for uploading, listing, and deleting PDFs.

## API Endpoints

Every route below is protected by dependency injection at `include_router()` time, so a new
route is protected by omission unless explicitly listed as public. See
`backend/tests/api/test_route_protection.py` for the enforced classification.

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
POST /api/query
```

Request body:

```json
{
  "conversation_id": "5b1f2e3a-2222-4444-8888-0123456789ab",
  "question": "Who is Nithusikan?",
  "top_k": 5
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

The server-side upload path is deliberately absent from `metadata` — the API schema drops it
so a client is never handed the filesystem layout of the server. Engine failures (Pinecone or
Gemini errors, which can carry credentials in their message text) are logged server-side and
returned to the client as a generic 502, never the raw exception text.

### Documents — admin-only

```http
POST   /api/ingest                        # multipart PDF upload
GET    /api/documents
DELETE /api/documents/{id}
POST   /api/documents/{id}/purge          # retry a failed deletion; sweeps orphan vectors
```

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

# One-time import of a legacy storage/bm25_corpus.json into Postgres
python scripts\migrate_bm25_corpus.py

# Destructive: drops and recreates the Pinecone index
python scripts\reset_pinecone.py
```

## Testing

Three kinds of suite, split by directory:

```powershell
# Engine — no external services
cd rag
python -m pytest tests\unit

# Backend unit + API — SQLite, no network; this is exactly what CI runs
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
lifespan and connect to the real database. `backend/tests/api/test_route_protection.py`
compares a hand-written public/authenticated/admin table against the routes the app actually
exposes, so adding an endpoint without deciding who may call it fails the build.

Frontend type-check and build:

```powershell
cd frontend
npm run build
```

## Current Implementation Notes

- The FastAPI app is built in `backend.app:create_app` and registers the health, auth,
  conversations, ingest, documents, and query routers.
- `backend.wiring.rag_factory` builds the embedder, vector store, reranker, and BM25 index as
  cached singletons. Ingesting or deleting a document calls `.rebuild()` on the BM25 index in
  place rather than tearing down and rebuilding the whole RAG service — the earlier design
  re-instantiated the embedder and reranker on every upload.
- Pinecone indexes are created automatically with cosine similarity in AWS `us-east-1`.
- Embedding and reranking use Pinecone's hosted inference by default
  (`USE_HOSTED_INFERENCE=true`); local Sentence Transformer / cross-encoder models are a
  fallback behind the `local-models` extra.
- `BM25Index` is loaded from the `document_chunks` table (via `PersistentConversationStore`'s
  sibling, the BM25 loader), not from a JSON file, so it reflects the database rather than
  whatever a file on disk happened to contain.
- Conversation memory is persisted in PostgreSQL per conversation and survives restarts.
- `top_k` is accepted by the query API; `candidate_k` defaults to `30` inside
  `HistoryAwareRAGService.answer_with_sources`.

## Known Limitations

- Text-based PDFs are supported; scanned PDFs need OCR before ingestion.
- There is no admin API for creating invite codes yet — insert a row into `invite_codes`
  directly, or run with `ALLOW_OPEN_REGISTRATION=true` for a small, trusted class.
- Google sign-in is deferred: `GOOGLE_CLIENT_ID` is read but nothing in the API or frontend
  uses it yet.
- There is no password reset flow (no email provider is configured).
- No rate limiting on `/api/auth/login` or `/api/query`.
- Pinecone index name is not separated per environment, so a document deleted in a
  development deployment is also deleted in production if they share `PINECONE_INDEX_NAME`.
- `frontend/vercel.json` ships with a placeholder backend URL that must be replaced before
  the production frontend can reach the API.
- API startup builds the embedder, vector store, BM25 index, and reranker clients, so cold
  start time depends on Pinecone/Gemini reachability even though no model weights are
  downloaded by default.

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
```

## Deployment

The intended shape is free-tier across the board: Vercel (frontend), Koyeb (backend
container), Supabase (PostgreSQL), Pinecone (vectors + hosted inference), GitHub Actions
(CI/CD). What's in the repository:

- **`Dockerfile`** (root): builds from the repo root since `backend` imports `rag`. No ML
  weights baked in — hosted inference means the image needs neither PyTorch nor
  sentence-transformers. Reads `$PORT` at runtime.
- **`.github/workflows/pr-checks.yml`**: on every PR — lint (ruff + black), engine tests,
  backend unit + API tests, a Docker build (not pushed), and a frontend build.
- **`.github/workflows/backend-deploy.yml`**: on push to `main` — tests, then
  `alembic upgrade head` against `DATABASE_URL`, then a Koyeb service redeploy. Migrations run
  before the deploy is triggered, deliberately, so new code never reaches a database that
  doesn't yet have the column it expects.
- **`frontend/vercel.json`**: rewrites `/api/*` and `/health/*` to the deployed backend URL,
  keeping the frontend and API same-origin from the browser's point of view — this is what
  lets the httpOnly refresh cookie work at all, since a cross-site cookie would otherwise be
  blocked. **The backend URL in this file is a placeholder (`REPLACE-ME.koyeb.app`)** and must
  be updated once the Koyeb service exists.

To actually deploy: create the Postgres database (e.g. a Supabase project), create the
Pinecone index, create a Koyeb service pointed at this repository's Dockerfile with the
environment variables from `backend/.env.example` set (including `COOKIE_SECURE=true` and,
once open registration should close, `ALLOW_OPEN_REGISTRATION=false`), set `KOYEB_API_TOKEN`
and `DATABASE_URL` as GitHub secrets and `KOYEB_SERVICE` as a repository variable, update
`vercel.json` with the real Koyeb URL, deploy the frontend to Vercel, and set `CORS_ORIGINS`
on the backend to the deployed frontend's origin.

## Recommended Next Improvements

1. Add an admin API for creating, listing, and revoking invite codes.
2. Wire up Google sign-in (verify the ID token server-side, link by verified email).
3. Add a password reset flow once an email provider is available.
4. Add rate limiting on `/api/auth/login` and `/api/query`.
5. Separate Pinecone indexes per environment.
6. Stream answers to the frontend instead of waiting for the full generation.
7. Add frontend tests (no runner is configured yet).

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
                     │ Chapter                               │
                     │   └── Section                         │
                     │         └── Subsection                │
                     │               └── Elements            │
                     │                                        │
                     │ Generate heading paths                │
                     │ Resolve parent references             │
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
        │      → one chunk                                          │
        │                                                          │
        │ If block is large                                         │
        │      → Parent chunk                                       │
        │      → Child chunks                                       │
        │                                                          │
        │ Every child inherits                                      │
        │ Chapter                                                   │
        │ Section                                                   │
        │ Heading Path                                              │
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
