# RAG Application

A Python Retrieval Augmented Generation application that ingests PDF documents, stores embeddings in Pinecone, retrieves relevant chunks, and answers questions with Google Gemini. The application also includes a conversation-aware RAG service with session memory, query rewriting, and summarization.

## Features

- PDF document loading with `pypdf`
- Text chunking with LangChain `RecursiveCharacterTextSplitter`
- Embeddings with Sentence Transformers
- Vector storage and semantic search with Pinecone
- Answer generation with Google Gemini
- FastAPI API with health, ingestion, and query endpoints
- Conversation-aware query handling using `conversation_id`
- Unit tests for core ingestion, retrieval, generation, and service behavior

## Project Structure

```text
rag_application/
+-- data/
|   +-- raw/
|       +-- cv.pdf
+-- scripts/
|   +-- ask_cv_from_terminal.py
|   +-- run_ingestion.py
|   +-- test_rag.py
|   +-- test_retrieval.py
+-- src/
|   +-- rag_application/
|       +-- api/
|       |   +-- app.py
|       |   +-- schemas.py
|       |   +-- routers/
|       |       +-- health.py
|       |       +-- ingest.py
|       |       +-- query.py
|       +-- config/
|       |   +-- component_configs.py
|       |   +-- settings.py
|       +-- conversation/
|       |   +-- memory.py
|       |   +-- query_rewriter.py
|       |   +-- schemas.py
|       |   +-- session_manager.py
|       |   +-- summarizer.py
|       +-- ingestion/
|       |   +-- chunker.py
|       |   +-- document_loader.py
|       |   +-- embedder.py
|       |   +-- pipeline.py
|       |   +-- processor.py
|       +-- llm/
|       |   +-- generator.py
|       |   +-- prompt_builder.py
|       |   +-- schemas.py
|       +-- retrieval/
|       |   +-- retriever.py
|       |   +-- schemas.py
|       |   +-- query_service.py
|       |   +-- hybrid_search.py
|       |   +-- reranker.py
|       +-- services/
|       |   +-- rag_service.py
|       |   +-- history_aware_rag_service.py
|       +-- vectorstore/
|       |   +-- base.py
|       |   +-- pinecone_store.py
|       +-- main.py
+-- tests/
|   +-- unit/
|   +-- integration/
+-- pyproject.toml
+-- README.md
```

## Architecture

The main RAG flow is:

```text
PDF file
  -> DocumentLoader
  -> TextChunker
  -> Embedder
  -> VectorDataProcessor
  -> PineconeVectorStore
  -> Retriever
  -> PromptBuilder
  -> GeminiGenerator
  -> Answer
```

The conversation-aware flow adds:

```text
conversation_id
  -> SessionManager
  -> ConversationMemory
  -> QueryRewriter
  -> Retriever
  -> PromptBuilder with summary and recent messages
  -> GeminiGenerator
  -> ConversationSummarizer when message count reaches the trigger
```

## Requirements

- Python 3.11 or newer
- Pinecone API key
- Pinecone index name
- Google Gemini API key
- Internet access for model/API calls

## Installation

From the project root:

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

Create a `.env` file in the project root.

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=your_pinecone_index_name
GEMINI_API_KEY=your_gemini_api_key

# Optional
CHUNK_SIZE=500
CHUNK_OVERLAP=50
RETRIEVAL_TOP_K=5
INITIAL_RETRIEVAL_K=20
RERANKING_K=8
FINAL_CONTEXT_K=5
SIMILARITY_THRESHOLD=0.7
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
GENERATION_MODEL_NAME=gemini-3.1-flash-lite
```

Required variables:

- `PINECONE_API_KEY`: API key used to connect to Pinecone.
- `PINECONE_INDEX_NAME`: Pinecone index to create/use.
- `GEMINI_API_KEY`: API key used by `google-genai`.

Optional variables:

- `CHUNK_SIZE`: Maximum chunk size used during PDF splitting.
- `CHUNK_OVERLAP`: Overlap between adjacent chunks.
- `RETRIEVAL_TOP_K`: Number of chunks returned for API query context.
- `EMBEDDING_MODEL_NAME`: Sentence Transformer model name.
- `GENERATION_MODEL_NAME`: Gemini model name.

## Running Ingestion

The default ingestion script reads:

```text
data/raw/cv.pdf
```

Run:

```powershell
python -m rag_application.main
```

Or:

```powershell
python scripts\run_ingestion.py
```

This will:

1. Load the PDF.
2. Split the extracted text into chunks.
3. Generate embeddings.
4. Prepare vector metadata.
5. Create the Pinecone index if it does not already exist.
6. Upsert vectors into Pinecone.

## Running The API

Start FastAPI with Uvicorn:

```powershell
uvicorn rag_application.api.app:app --reload
```

Default local URL:

```text
http://127.0.0.1:8000
```

Interactive API docs:

```text
http://127.0.0.1:8000/docs
```

## API Endpoints

### Health Check

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

### Ingest A PDF

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

Note: this endpoint currently accepts a server-local PDF file path. Multipart file upload is not implemented yet.

### Query Documents

```http
POST /api/query
```

Request body:

```json
{
  "conversation_id": "demo-session-1",
  "question": "Who is Nithusikan?"
}
```

Example:

```powershell
curl -X POST http://127.0.0.1:8000/api/query `
  -H "Content-Type: application/json" `
  -d "{\"conversation_id\":\"demo-session-1\",\"question\":\"Who is Nithusikan?\"}"
```

Response shape:

```json
{
  "question": "Who is Nithusikan?",
  "answer": "Generated answer from the retrieved document context.",
  "source_documents": [
    "Relevant source chunk text..."
  ]
}
```

The same `conversation_id` should be reused for follow-up questions so the history-aware service can rewrite context-dependent questions.

## Terminal Chat

After ingestion, you can use the terminal conversation script:

```powershell
python scripts\ask_cv_from_terminal.py
```

With an initial question:

```powershell
python scripts\ask_cv_from_terminal.py "Who is the person in the CV?"
```

## Testing

Run unit tests:

```powershell
python -m pytest tests\unit
```

Expected current result:

```text
28 passed
```

Run all tests:

```powershell
python -m pytest
```

Important: integration tests may require valid Pinecone/Gemini credentials, network access, and previously ingested data. Treat them separately from the unit suite.

## Current Status

Completed:

- Core ingestion pipeline.
- Pinecone vector storage.
- Semantic retrieval.
- Gemini answer generation wrapper.
- Basic RAG service.
- History-aware RAG service.
- FastAPI health endpoint.
- FastAPI query endpoint.
- FastAPI ingestion endpoint for server-local PDFs.
- Unit test suite passing.

Partially implemented:

- Conversation memory is in-memory only.
- Query rewriting and summarization use the same Gemini configuration as final generation.
- `hybrid_search.py` and `reranker.py` are placeholders.
- Integration tests need cleanup and clearer separation from unit tests.

Not implemented yet:

- Multipart PDF upload endpoint.
- Persistent chat/session storage.
- Authentication.
- Rate limiting.
- Docker setup.
- CI workflow.
- Structured source citations with page numbers.
- Reranking and hybrid retrieval.
- Evaluation dataset and answer-quality metrics.

## Known Limitations

- The app currently supports text-based PDFs. Scanned image PDFs need OCR before ingestion.
- Pinecone index creation is automatic, but index dimension must match the embedding model.
- Conversation memory resets when the process restarts.
- The ingestion endpoint reads files from the server filesystem, not from browser upload.
- Source documents are returned as raw chunk text.
- Real Gemini and Pinecone calls can be slow and cost money.

## Recommended Next Improvements

1. Add multipart PDF upload using FastAPI `UploadFile`.
2. Add page-aware chunk metadata so answers can cite source pages.
3. Add a persistent session store such as SQLite, Postgres, or Redis.
4. Add integration test markers such as `@pytest.mark.integration`.
5. Add a reranker after initial Pinecone retrieval.
6. Add hybrid retrieval using lexical and vector search.
7. Add Docker and `.env.example`.
8. Add GitHub Actions or another CI workflow for linting and tests.
9. Add structured logging and request IDs.
10. Add user-facing error handling for missing API keys, empty indexes, and model failures.

## Useful Commands

Format code:

```powershell
black src tests
```

Lint code:

```powershell
ruff check src tests
```

Run API:

```powershell
uvicorn rag_application.api.app:app --reload
```

Run ingestion:

```powershell
python -m rag_application.main
```

Run unit tests:

```powershell
python -m pytest tests\unit
```
