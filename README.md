# RAG Application

A Python Retrieval Augmented Generation application for PDF documents. It loads text from PDFs, chunks the content, stores dense embeddings in Pinecone, retrieves relevant context, reranks candidate chunks, and answers questions with Google Gemini. The API also keeps short-lived conversation memory so follow-up questions can be rewritten into standalone retrieval queries.

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

```text
rag_application/
|-- data/
|-- scripts/
|   |-- ask_cv_from_terminal.py
|   |-- run_ingestion.py
|   |-- test_rag.py
|   `-- test_retrieval.py
|-- src/
|   `-- rag_application/
|       |-- api/
|       |   |-- app.py
|       |   |-- dependencies.py
|       |   |-- schemas.py
|       |   `-- routers/
|       |       |-- health.py
|       |       |-- ingest.py
|       |       `-- query.py
|       |-- config/
|       |-- conversation/
|       |-- indexes/
|       |-- ingestion/
|       |-- llm/
|       |-- retrieval/
|       |-- services/
|       |-- utils/
|       |-- vectorstore/
|       |-- wiring/
|       `-- main.py
|-- storage/
|   `-- bm25_corpus.json
|-- tests/
|   |-- integration/
|   `-- unit/
|-- pyproject.toml
`-- README.md
```

## Requirements

- Python 3.11 or newer
- Pinecone API key
- Pinecone index name
- Google Gemini API key
- Network access for Pinecone, Gemini, and model downloads

The first run may download Sentence Transformer and CrossEncoder model weights.

## Installation

From the project root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Environment Variables

Create a `.env` file in the project root:

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

The default ingestion script expects:

```text
data/raw/cv.pdf
```

Run either command:

```powershell
python -m rag_application.main
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

Start the FastAPI app:

```powershell
uvicorn rag_application.api.app:app --reload
```

Local URLs:

```text
API:  http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs
```

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

Request body:

```json
{
  "file_path": "E:\\Learning\\RAG Applications\\rag_application\\data\\raw\\cv.pdf"
}
```

Example:

```powershell
curl -X POST http://127.0.0.1:8000/api/ingest `
  -H "Content-Type: application/json" `
  -d "{\"file_path\":\"E:\\Learning\\RAG Applications\\rag_application\\data\\raw\\cv.pdf\"}"
```

Response:

```json
{
  "file_path": "E:\\Learning\\RAG Applications\\rag_application\\data\\raw\\cv.pdf",
  "status": "success",
  "message": "Document ingested successfully."
}
```

This endpoint accepts a server-local PDF path. Multipart upload is not implemented.

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

Run a conversational terminal session:

```powershell
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

Run unit tests:

```powershell
python -m pytest tests\unit
```

Run the full suite:

```powershell
python -m pytest
```

Integration tests may require real Pinecone/Gemini credentials, network access, model downloads, and previously ingested data.

## Current Implementation Notes

- The FastAPI app is built in `rag_application.api.app:create_app` and registers health, ingestion, and query routers.
- `build_history_aware_rag_service()` wires the runtime RAG service at API startup.
- Pinecone indexes are created automatically with cosine similarity in AWS `us-east-1`.
- Ingestion writes `storage/bm25_corpus.json`, but the current service factory initializes `BM25Index(documents=[])`. Until the stored corpus is loaded into the factory, BM25 contributes no results after startup and the hybrid retriever effectively relies on dense retrieval.
- Conversation memory is process-local and resets when the app restarts.
- Source metadata does not yet include accurate PDF page numbers.
- `top_k` is accepted by the query API; `candidate_k` defaults to `30` inside `HistoryAwareRAGService.answer_with_sources`.

## Known Limitations

- Text-based PDFs are supported. Scanned PDFs need OCR before ingestion.
- The ingestion endpoint reads from the server filesystem rather than uploaded browser files.
- API startup loads the embedding model, Pinecone client, Gemini client, and reranker, so cold start can be slow.
- Real Pinecone, Gemini, and model-download calls require network access and can incur cost.
- Session history is not persisted in a database.
- Authentication, rate limiting, Docker, CI, and production deployment configuration are not included yet.

## Useful Commands

```powershell
# Format
black src tests

# Lint
ruff check src tests

# Run API
uvicorn rag_application.api.app:app --reload

# Run ingestion
python -m rag_application.main

# Run unit tests
python -m pytest tests\unit
```

## Recommended Next Improvements

1. Load `storage/bm25_corpus.json` into `BM25Index` during service startup.
2. Add multipart PDF upload using FastAPI `UploadFile`.
3. Preserve page numbers in chunk metadata for real citations.
4. Add persistent conversation storage with SQLite, Postgres, or Redis.
5. Add `pytest` markers for integration tests.
6. Move reranker model name and retrieval defaults fully into settings.
7. Add `.env.example`, Docker, and CI.
8. Add structured API errors for missing credentials, empty indexes, and model failures.
