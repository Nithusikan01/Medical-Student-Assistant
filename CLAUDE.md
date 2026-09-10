# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A full-stack RAG (Retrieval-Augmented Generation) application over PDF documents. It extracts text from PDFs, chunks it, embeds it with Sentence Transformers, stores/retrieves vectors in Pinecone, fuses dense retrieval with BM25 lexical retrieval, reranks with a cross-encoder, and generates answers with Google Gemini. Conversation memory lets follow-up questions get rewritten into standalone retrieval queries. A React + TypeScript frontend provides upload and chat.

## Repository layout

Three top-level parts, two of them installable Python packages:

- `rag/` — the RAG engine, package `rag_application`. Pure library: no FastAPI, no HTTP. Contains `config/`, `conversation/`, `evaluation/`, `indexes/`, `ingestion/`, `llm/`, `retrieval/`, `services/`, `utils/`, `vectorstore/`, plus its own `tests/`.
- `backend/` — the FastAPI layer, package `api_app`. Contains `app.py`, `dependencies.py`, `schemas.py`, `routers/`, `services/` (upload handling), and `wiring/rag_factory.py` (the composition root). Also holds `scripts/`, `.env`, `data/`, and `storage/`.
- `frontend/` — Vite + React + TypeScript web app.

`backend` depends on `rag`; `rag` must never import `api_app`. `backend/` is the runtime root: `.env`, `data/raw/`, and `storage/` are resolved relative to it, so run uvicorn and the scripts from inside `backend/`.

## Commands

Install (editable, with dev deps) — `rag` first, since `backend` imports it:

```powershell
python -m pip install -e ".\rag[dev]"
python -m pip install -e ".\backend[dev]"
cd frontend; npm install
```

Run tests (each package owns its suite; `pythonpath` is configured in each `pyproject.toml`, so no install is strictly needed):

```powershell
cd rag; python -m pytest tests\unit     # engine unit tests, no external services
cd rag; python -m pytest                # adds engine integration tests
cd backend; python -m pytest            # API/wiring integration tests
cd rag; python -m pytest tests\unit\test_pipeline.py::test_ingestion_pipeline_runs_all_steps
```

Integration tests hit real Pinecone/Gemini and download model weights on first run — they `pytest.skip()` themselves unless `RUN_REAL_RAG_TESTS=1` and credentials are present, so don't assume a green run means credentials are configured. Note `rag/tests/unit/test_embedder.py::test_embed_single_chunk` fails on a pre-existing mock-call-count assertion, unrelated to wiring.

Format and lint:

```powershell
black rag\src rag\tests backend\src backend\tests
ruff check rag\src rag\tests backend\src backend\tests
```

Run the API and the frontend (two terminals):

```powershell
cd backend; uvicorn api_app.app:app --reload
cd frontend; npm run dev
```

The Vite dev server (port 5173) proxies `/api` and `/health` to `http://127.0.0.1:8000`; override with `VITE_BACKEND_URL` in `frontend/.env` or the shell (`vite.config.ts` reads it via `loadEnv`, so both work). `npm run build` runs `tsc -b` first, so it also type-checks.

Ingestion runs through `POST /api/ingest` (multipart upload) or the frontend's upload panel — there is no CLI ingestion entry point (`main.py` was deleted). Ad-hoc scripts in `backend/scripts/` are for manual smoke testing, not part of the test suite: `ask_cv_from_terminal.py` (interactive Q&A), `test_rag.py` / `test_retrieval.py` / `test_reranker.py` (component smoke tests), `run_ingestion.py` (BM25 corpus verification, despite the name), `evaluate_rag.py` (currently broken — imports `rag_application.evaluation` modules that don't exist), `reset_pinecone.py` (drops and recreates the Pinecone index — destructive).

Required environment variables (`.env` in `backend/`, templated by `backend/.env.example`): `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `GEMINI_API_KEY`. The example file documents every optional tuning variable (`CHUNK_SIZE`, `CANDIDATE_K`, `EMBEDDING_MODEL_NAME`, etc.) — they're all read in `rag/src/rag_application/config/settings.py::load_settings`. `.env` files are gitignored at any depth; `.env.example` files are committed.

## Architecture

### Two independent pipelines, one wiring point

Everything is assembled through dependency injection, not framework magic. The two pipelines share components (`Embedder`, `PineconeVectorStore`) but are built separately:

- **Ingestion** (`rag_application/ingestion/pipeline.py::IngestionPipeline.ingest`) is constructed per-request in `api_app/routers/ingest.py::get_ingestion_pipeline()`.
- **Query** (`rag_application/services/history_aware_rag_service.py::HistoryAwareRAGService`) is built once by `api_app/wiring/rag_factory.py::build_history_aware_rag_service()` — an `@lru_cache()`d factory called at API startup (`api_app/app.py` lifespan) and re-invoked after every ingest (`ingest.py` calls `.cache_clear()` then rebuilds it, so newly-ingested documents become queryable without an app restart).

When changing how a component is constructed (e.g. adding a retriever, changing model names), `rag_factory.py` is the single place that wires it into the live query path. It lives in `backend/` because it is application composition, not library code — the `rag` package deliberately ships no composition root.

### Ingestion path

```
PDF file -> DocumentLoader -> TextChunker -> Embedder -> VectorDataProcessor -> PineconeVectorStore
                                    |
                                    +--> BM25CorpusBuilder -> storage/bm25_corpus.json
```

`IngestionPipeline.ingest()` batches chunks (`batch_size`) and, for each batch, upserts to Pinecone *and* appends to the BM25 corpus file in the same loop — both are written incrementally per document, not as a single bulk pass at the end. If `bm25_corpus_path` is `None` the BM25 side is skipped entirely (a `_NullContext` stands in for the builder). `BM25CorpusBuilder` is a context manager: normal exit calls `finish()` (atomically replaces the corpus file), an exception calls `abort()` (deletes the partial temp file) — see `ingestion/bm25/corpus_builder.py`.

### Query path

```
conversation_id + question
  -> SessionManager (per-conversation ConversationMemory, in-process, resets on restart)
  -> QueryRewriter (LLM call: folds conversation history into a standalone query)
  -> HybridRetriever
       -> DenseRetriever -> PineconeVectorStore
       -> BM25Retriever  -> BM25Index (loaded from storage/bm25_corpus.json at factory build time)
       (fused via Reciprocal Rank Fusion, see hybrid_retriever.py)
  -> Reranker (cross-encoder, BAAI/bge-reranker-base)
  -> PromptBuilder -> GeminiGenerator
  -> answer + structured RetrievedChunk sources
  -> ConversationMemory updated; summarized once message count hits HistoryAwareRAGService.SUMMARY_TRIGGER
```

Because `BM25Index` is built once at factory-construction time from whatever `bm25_corpus.json` contains, BM25 results only reflect documents ingested *before* the service was last (re)built — this is exactly why `ingest.py` clears the factory cache and rebuilds after every ingest.

### Data model chain (why there are five near-identical "chunk" types)

Each ingestion/retrieval stage has its own dataclass rather than one mutable object threaded through, so trace metadata by stage:

All under `rag/src/rag_application/` unless noted:

1. `ingestion/schemas.py`: `LoadedPage`/`LoadedDocument` (raw text) -> `ChunkMetadata`/`DocumentChunk` (post-chunking) -> `EmbeddedChunk` (adds `embedding`).
2. `vectorstore/schemas.py`: `VectorRecord`/`VectorRecordMetadata` (what's sent to Pinecone — `to_dict()` drops `None` fields because Pinecone rejects null metadata values) and `SearchResult` (what comes back from a query).
3. `retrieval/schemas.py`: `RetrievedChunk`/`RetrievedChunkMetadata` (post-retrieval/rerank, carries `dense_score`/`bm25_score`/`hybrid_score`/`rerank_score`/`retrieval_method`).

`ChunkMetadata` is the canonical field set (document_id, filename, source_path, page_number, section_title, heading_level, start_char/end_char, chunk_size, overlap_size, element_id/type, language, tags); the other metadata dataclasses mirror it for their stage. When adding a metadata field, it typically needs updating in all three places plus `BM25Metadata` (`ingestion/bm25/schemas.py`), the API's `SourceMetadata` (`backend/src/api_app/schemas.py`), and the mirrored TypeScript interface in `frontend/src/types.ts`.

### Config

`config/settings.py::Settings` is a frozen dataclass populated from env vars by `load_settings()`; component-specific config is carved out via `Settings.<x>_config()` methods returning the small dataclasses in `config/component_configs.py` (`EmbeddingConfig`, `ChunkingConfig`, `GenerationConfig`, `PineconeConfig`, `RetrievalConfig`). Components take their narrow config dataclass in `__init__`, not the whole `Settings` object — follow that pattern for new components.

### Heavy imports are lazy

`sentence-transformers` (`Embedder`, `Reranker`, `DenseRetriever`) and `langchain-text-splitters` (`TextChunker`) are imported inside constructors/builders, not at module top level, so importing these modules doesn't force a slow ML-library load for code paths that don't need it (e.g. API startup before the factory runs, or CLI scripts that only touch schemas).

### API surface

Two routers under `/api`: `POST /api/ingest` (multipart PDF upload via `api_app/services/upload_service.py`, which saves to `backend/storage/uploads/` and deletes it in a `finally` block) and `POST /api/query` (JSON body, depends on `app.state.rag_service` via `api_app/dependencies.py`). Query top_k is bounded `1..20` via a pydantic `Field` constraint in `api_app/schemas.py`. Health is `GET /health/health` (the router is mounted under a `/health` prefix and declares `/health` itself).

### Frontend

Vite + React 18 + TypeScript, no UI framework or state library — plain hooks and one CSS file (`src/index.css`). `src/api/client.ts` is the only place that talks to the backend; it uses relative URLs (`/api/...`, `/health/health`) so the Vite proxy handles dev routing and no base URL is baked into the bundle. `src/types.ts` mirrors the pydantic response models by hand — keep it in sync when API schemas change. `useConversation` owns chat state and generates a `conversation_id` with `crypto.randomUUID()` per session; "New conversation" mints a fresh id, which is what resets server-side memory association. Backend CORS already allows `localhost:5173` for running the frontend without the proxy.
