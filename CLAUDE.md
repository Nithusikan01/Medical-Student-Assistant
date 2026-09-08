# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python RAG (Retrieval-Augmented Generation) application over PDF documents. It extracts text from PDFs, chunks it, embeds it with Sentence Transformers, stores/retrieves vectors in Pinecone, fuses dense retrieval with BM25 lexical retrieval, reranks with a cross-encoder, and generates answers with Google Gemini. Conversation memory lets follow-up questions get rewritten into standalone retrieval queries.

## Commands

Install (editable, with dev deps):

```powershell
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
python -m pytest tests\unit          # unit tests only (no external services needed)
python -m pytest                     # full suite, including integration tests
python -m pytest tests\unit\test_pipeline.py::test_ingestion_pipeline_runs_all_steps  # single test
```

Integration tests (`tests/integration/`) hit real Pinecone/Gemini and download model weights on first run — they `pytest.skip()` themselves when required fixtures/credentials aren't available, so don't assume a green run means credentials are configured.

Format and lint:

```powershell
black src tests
ruff check src tests
```

Run the API:

```powershell
uvicorn rag_application.api.app:app --reload
```

Run ingestion from the CLI (defaults to `data/raw/cv.pdf`):

```powershell
python -m rag_application.main
python scripts\run_ingestion.py
```

Ad-hoc terminal scripts (`scripts/`) are for manual smoke testing, not part of the test suite: `ask_cv_from_terminal.py` (interactive Q&A), `test_rag.py` / `test_retrieval.py` / `test_reranker.py` (component smoke tests), `evaluate_rag.py` (runs the pipeline against a labeled dataset in `data/evaluation/`), `reset_pinecone.py` (drops and recreates the Pinecone index — destructive).

Required environment variables (`.env` in project root): `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `GEMINI_API_KEY`. See `README.md` for the full list of optional tuning variables (`CHUNK_SIZE`, `CANDIDATE_K`, `EMBEDDING_MODEL_NAME`, etc.) — they're all read in `config/settings.py::load_settings`.

## Architecture

### Two independent pipelines, one wiring point

Everything is assembled through dependency injection, not framework magic. The two pipelines share components (`Embedder`, `PineconeVectorStore`) but are built separately:

- **Ingestion** (`ingestion/pipeline.py::IngestionPipeline.ingest`) is constructed per-request in `api/routers/ingest.py::get_ingestion_pipeline()`.
- **Query** (`services/history_aware_rag_service.py::HistoryAwareRAGService`) is built once by `wiring/rag_factory.py::build_history_aware_rag_service()` — an `@lru_cache()`d factory called at API startup (`api/app.py` lifespan) and re-invoked after every ingest (`ingest.py` calls `.cache_clear()` then rebuilds it, so newly-ingested documents become queryable without an app restart).

When changing how a component is constructed (e.g. adding a retriever, changing model names), `rag_factory.py` is the single place that wires it into the live query path.

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

1. `ingestion/schemas.py`: `LoadedPage`/`LoadedDocument` (raw text) -> `ChunkMetadata`/`DocumentChunk` (post-chunking) -> `EmbeddedChunk` (adds `embedding`).
2. `vectorstore/schemas.py`: `VectorRecord`/`VectorRecordMetadata` (what's sent to Pinecone — `to_dict()` drops `None` fields because Pinecone rejects null metadata values) and `SearchResult` (what comes back from a query).
3. `retrieval/schemas.py`: `RetrievedChunk`/`RetrievedChunkMetadata` (post-retrieval/rerank, carries `dense_score`/`bm25_score`/`hybrid_score`/`rerank_score`/`retrieval_method`).

`ChunkMetadata` is the canonical field set (document_id, filename, source_path, page_number, section_title, heading_level, start_char/end_char, chunk_size, overlap_size, element_id/type, language, tags); the other metadata dataclasses mirror it for their stage. When adding a metadata field, it typically needs updating in all three places plus `BM25Metadata` (`ingestion/bm25/schemas.py`) and the API's `SourceMetadata` (`api/schemas.py`).

### Config

`config/settings.py::Settings` is a frozen dataclass populated from env vars by `load_settings()`; component-specific config is carved out via `Settings.<x>_config()` methods returning the small dataclasses in `config/component_configs.py` (`EmbeddingConfig`, `ChunkingConfig`, `GenerationConfig`, `PineconeConfig`, `RetrievalConfig`). Components take their narrow config dataclass in `__init__`, not the whole `Settings` object — follow that pattern for new components.

### Heavy imports are lazy

`sentence-transformers` (`Embedder`, `Reranker`, `DenseRetriever`) and `langchain-text-splitters` (`TextChunker`) are imported inside constructors/builders, not at module top level, so importing these modules doesn't force a slow ML-library load for code paths that don't need it (e.g. API startup before the factory runs, or CLI scripts that only touch schemas).

### API surface

Two routers under `/api`: `POST /api/ingest` (multipart PDF upload — despite what `README.md` says about a `file_path` JSON body, the current implementation is `UploadFile` via `api/services/upload_service.py`, which saves to `storage/uploads/` and deletes it in a `finally` block) and `POST /api/query` (JSON body, depends on `app.state.rag_service` via `api/dependencies.py`). Query top_k is bounded `1..20` via a pydantic `Field` constraint in `api/schemas.py`.
