# RAG Application

A full-stack Retrieval Augmented Generation application for PDF documents: a
Python RAG engine, a FastAPI backend, and a React + TypeScript web app. It loads text from PDFs, chunks the content, stores dense embeddings in Pinecone, retrieves relevant context, reranks candidate chunks, and answers questions with Google Gemini. The API also keeps short-lived conversation memory so follow-up questions can be rewritten into standalone retrieval queries.

## Current Capabilities

- PDF text extraction with `pypdf`
- Recursive text chunking with LangChain text splitters
- Sentence Transformer embeddings
- Pinecone vector index creation, upsert, query, and delete support
- Dense semantic retrieval from Pinecone
- BM25 lexical retrieval primitives with `rank-bm25`
- Hybrid retrieval with Reciprocal Rank Fusion across dense and BM25 results
- Cross-encoder reranking with `BAAI/bge-reranker-base`
- Gemini generation through `google-genai` with retry handling and latency metadata
- Conversation-aware query rewriting, recent-message memory, and summarization
- FastAPI health, ingestion, and query endpoints
- Structured source chunks in query responses
- React + TypeScript web app with PDF upload, conversational chat, and per-answer source inspection
- Unit and integration tests for ingestion, retrieval, generation, settings, and service behavior

## Architecture

The ingestion path is:

```text
PDF file
  -> DocumentLoader
  -> TextChunker
  -> Embedder
  -> VectorDataProcessor
  -> PineconeVectorStore
  -> storage/bm25_corpus.json
```

The query path is:

```text
conversation_id + question
  -> SessionManager
  -> ConversationMemory
  -> QueryRewriter
  -> HybridRetriever
       -> DenseRetriever -> Pinecone
       -> BM25Retriever  -> BM25Index
  -> Reranker
  -> PromptBuilder
  -> GeminiGenerator
  -> answer + structured sources
```

## Project Structure

The repository is a monorepo with three top-level parts:

```text
Medical-Student-Assistant/
|-- rag/                          # RAG engine (importable library, no HTTP)
|   |-- pyproject.toml            # package: rag_application
|   |-- src/rag_application/
|   |   |-- config/               # Settings + per-component config dataclasses
|   |   |-- conversation/         # memory, query rewriting, summarization
|   |   |-- evaluation/
|   |   |-- indexes/              # BM25Index
|   |   |-- ingestion/            # loader, chunker, embedder, pipeline, bm25 corpus
|   |   |-- llm/                  # Gemini generator + prompt builder
|   |   |-- retrieval/            # dense, bm25, hybrid, reranker, query service
|   |   |-- services/             # HistoryAwareRAGService
|   |   |-- utils/
|   |   `-- vectorstore/          # Pinecone store
|   `-- tests/
|       |-- fixtures/
|       |-- integration/
|       `-- unit/
|-- backend/                      # FastAPI HTTP layer (runtime root)
|   |-- pyproject.toml            # package: api_app
|   |-- .env                      # credentials live here
|   |-- data/raw/                 # source PDFs
|   |-- storage/                  # bm25_corpus.json, uploads/
|   |-- scripts/                  # ad-hoc smoke-test / maintenance scripts
|   |-- src/api_app/
|   |   |-- app.py                # create_app + lifespan
|   |   |-- dependencies.py
|   |   |-- schemas.py            # request/response models
|   |   |-- routers/              # health, ingest, query
|   |   |-- services/             # upload handling
|   |   `-- wiring/               # rag_factory: builds the live RAG service
|   `-- tests/integration/
`-- frontend/                     # React + TypeScript (Vite) web app
    |-- package.json
    |-- vite.config.ts            # proxies /api and /health to the backend
    `-- src/
        |-- api/                  # typed fetch client
        |-- components/           # ChatPanel, SourceList, UploadPanel
        `-- hooks/                # useConversation
```

`backend` depends on `rag`; `rag` never imports `backend`. The composition root
that assembles the engine into a live service is
`backend/src/api_app/wiring/rag_factory.py`.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer (for the frontend)
- Pinecone API key
- Pinecone index name
- Google Gemini API key
- Network access for Pinecone, Gemini, and model downloads

The first run may download Sentence Transformer and CrossEncoder model weights.

## Installation

Both Python packages are installed in editable mode. Install `rag` first, since
`backend` imports it.

From the project root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\rag[dev]"
python -m pip install -e ".\backend[dev]"
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

`backend/.env.example` documents every variable with its default. The frontend
has its own optional `frontend/.env.example`, whose only knob is
`VITE_BACKEND_URL`. Both `.env` files are gitignored; the `.env.example` files
are committed.

A filled-in `backend/.env` looks like:

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=your_pinecone_index_name
GEMINI_API_KEY=your_gemini_api_key

# Optional
CHUNK_SIZE=500
CHUNK_OVERLAP=50
CANDIDATE_K=20
DENSE_TOP_K=20
RERANKING_K=8
FINAL_CONTEXT_K=5
SIMILARITY_THRESHOLD=0.7
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
GENERATION_MODEL_NAME=gemini-3.1-flash-lite
```

Required variables:

- `PINECONE_API_KEY`: API key used to connect to Pinecone.
- `PINECONE_INDEX_NAME`: Pinecone index to create or reuse.
- `GEMINI_API_KEY`: API key used by the Gemini client.

Optional variables:

- `CHUNK_SIZE` and `CHUNK_OVERLAP`: PDF chunking controls.
- `CANDIDATE_K`: number of retrieval candidates requested before reranking.
- `DENSE_TOP_K`: dense retrieval setting reserved in configuration.
- `RERANKING_K`: reranking setting reserved in configuration.
- `FINAL_CONTEXT_K`: final context setting reserved in configuration.
- `SIMILARITY_THRESHOLD`: retrieval threshold setting reserved in configuration.
- `EMBEDDING_MODEL_NAME`: Sentence Transformer model name.
- `GENERATION_MODEL_NAME`: Gemini model name.

## Running Ingestion

Ingestion runs through the API (`POST /api/ingest`, multipart upload) or through
the frontend's upload panel. Uploaded PDFs are written to
`backend/storage/uploads/`, ingested, and then deleted.

`backend/scripts/run_ingestion.py` is a BM25 corpus verification script rather
than a general ingestion entry point: it chunks `backend/data/raw/cv.pdf`,
writes `backend/storage/test_bm25.json`, and asserts the records match the
chunks. Run it from the `backend/` directory:

```powershell
cd backend
python scripts\run_ingestion.py
```

Ingestion will:

1. Load text from the PDF.
2. Split the text into structured chunks.
3. Generate embeddings.
4. Prepare Pinecone vector payloads with metadata.
5. Create the Pinecone index if it does not exist.
6. Upsert vectors into Pinecone.
7. Write `storage/bm25_corpus.json` with chunk ids and text.

## Running The API

Start the FastAPI app from the `backend/` directory, which is the runtime root
for `.env`, `data/`, and `storage/`:

```powershell
cd backend
uvicorn api_app.app:app --reload
```

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

The app is served at `http://localhost:5173`. The Vite dev server proxies
`/api` and `/health` to `http://127.0.0.1:8000`, so no CORS configuration is
needed in development. Point it at a different backend by setting
`VITE_BACKEND_URL`, either in `frontend/.env` or as a shell variable. Build for
production with `npm run build`.

The UI provides PDF upload, a chat view that keeps one `conversation_id` per
session so follow-up questions get rewritten server-side, a per-answer source
list showing filename, page, chunk index, retrieval method and score, and a
`top_k` control bound to the API's `1..20` range.

## API Endpoints

### Health

```http
GET /health/health
```

Example:

```powershell
curl http://127.0.0.1:8000/health/health
```

Response:

```json
{
  "status": "healthy"
}
```

### Ingest PDF

```http
POST /api/ingest
```

Multipart form upload with a single `file` field. Only PDFs are accepted.

Example:

```powershell
curl -X POST http://127.0.0.1:8000/api/ingest `
  -F "file=@data/raw/cv.pdf;type=application/pdf"
```

Response:

```json
{
  "filename": "cv.pdf",
  "status": "success",
  "message": "Document ingested successfully."
}
```

After a successful ingest the service factory cache is cleared and the RAG
service is rebuilt, so newly ingested documents are queryable without an app
restart.

### Query Documents

```http
POST /api/query
```

Request body:

```json
{
  "conversation_id": "demo-session-1",
  "question": "Who is Nithusikan?",
  "top_k": 5
}
```

Example:

```powershell
curl -X POST http://127.0.0.1:8000/api/query `
  -H "Content-Type: application/json" `
  -d "{\"conversation_id\":\"demo-session-1\",\"question\":\"Who is Nithusikan?\",\"top_k\":5}"
```

Response shape:

```json
{
  "question": "Who is Nithusikan?",
  "answer": "Generated answer from the retrieved document context.",
  "sources": [
    {
      "id": "cv.pdf_chunk_0",
      "score": 0.91,
      "text": "Relevant source chunk text...",
      "metadata": {
        "source": "cv.pdf",
        "chunk_id": 0,
        "timestamp": 1783000000
      },
      "retrieval_method": "rerank(hybrid)"
    }
  ]
}
```

Reuse the same `conversation_id` for follow-up questions. The service stores in-memory history for that conversation, rewrites follow-up questions for retrieval, and summarizes after the configured message trigger.

## Terminal Scripts

All scripts live in `backend/scripts/` and are run from the `backend/`
directory.

Run a conversational terminal session:

```powershell
cd backend
python scripts\ask_cv_from_terminal.py
```

Start with an initial question:

```powershell
python scripts\ask_cv_from_terminal.py "Who is the person in the CV?"
```

Run a simple RAG smoke test:

```powershell
python scripts\test_rag.py
```

Run a dense retrieval smoke test:

```powershell
python scripts\test_retrieval.py
```

## Testing

Each package owns its own test suite.

```powershell
# Engine tests
cd rag
python -m pytest tests\unit
python -m pytest

# API tests
cd backend
python -m pytest
```

Integration tests may require real Pinecone/Gemini credentials, network access, model downloads, and previously ingested data. They skip themselves when `RUN_REAL_RAG_TESTS=1` is not set, so a green run does not mean credentials are configured.

Frontend type-check and build:

```powershell
cd frontend
npm run build
```

## Current Implementation Notes

- The FastAPI app is built in `api_app.app:create_app` and registers health, ingestion, and query routers.
- `api_app.wiring.rag_factory.build_history_aware_rag_service()` wires the runtime RAG service at API startup and is rebuilt after every ingest.
- Pinecone indexes are created automatically with cosine similarity in AWS `us-east-1`.
- `BM25Index` is built from `backend/storage/bm25_corpus.json` when the factory runs, so BM25 results reflect whatever was ingested before the service was last built.
- Conversation memory is process-local and resets when the app restarts.
- `top_k` is accepted by the query API; `candidate_k` defaults to `30` inside `HistoryAwareRAGService.answer_with_sources`.

## Known Limitations

- Text-based PDFs are supported. Scanned PDFs need OCR before ingestion.
- Each ingestion rewrites `bm25_corpus.json` from scratch rather than appending, so BM25 only covers the most recently ingested document. Dense retrieval still covers everything in Pinecone.
- `DocumentLoader` assigns a fresh UUID per load, so re-ingesting the same PDF adds duplicate vectors instead of replacing the old ones.
- API startup loads the embedding model, Pinecone client, Gemini client, and reranker, so cold start can be slow.
- Real Pinecone, Gemini, and model-download calls require network access and can incur cost.
- Session history is not persisted in a database.
- Authentication, rate limiting, Docker, CI, and production deployment configuration are not included yet.

## Useful Commands

```powershell
# Format
black rag\src rag\tests backend\src backend\tests

# Lint
ruff check rag\src rag\tests backend\src backend\tests

# Run API
cd backend; uvicorn api_app.app:app --reload

# Run frontend
cd frontend; npm run dev

# Run engine unit tests
cd rag; python -m pytest tests\unit
```

## Recommended Next Improvements

1. Append to `bm25_corpus.json` across ingestions instead of overwriting it.
2. Derive stable document ids from file content so re-ingestion replaces rather than duplicates.
3. Add persistent conversation storage with SQLite, Postgres, or Redis.
4. Add `pytest` markers for integration tests.
5. Move reranker model name and retrieval defaults fully into settings.
6. Add Docker and CI.
7. Add structured API errors for missing credentials, empty indexes, and model failures.
8. Stream answers to the frontend instead of waiting for the full generation.


## Current Plan

```Ingestion Pipeline

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
              Chroma / Pinecone / Qdrant / Weaviate

```
