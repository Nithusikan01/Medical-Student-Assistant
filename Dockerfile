# Backend image for Hugging Face Spaces.
#
# The build context is the repository root, because the API package imports
# the engine package and both must be present.
#
# Deliberately no ML model weights: embedding and reranking run on Pinecone's
# hosted inference, so this image needs neither PyTorch nor
# sentence-transformers, and a cold start does not wait on a model download.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Spaces runs containers as uid 1000; matching it keeps the writable
# directories owned by the runtime user.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Dependency metadata first, so edits to source do not invalidate the
# dependency layer.
COPY rag/pyproject.toml ./rag/
COPY backend/pyproject.toml ./backend/
RUN python -m pip install --upgrade pip setuptools wheel

COPY rag/ ./rag/
COPY backend/ ./backend/

# Editable installs keep the source at a predictable path, so alembic.ini and
# the migrations directory resolve exactly as they do in development.
RUN pip install -e ./rag -e ./backend

# Uploads land here briefly before ingestion deletes them.
RUN mkdir -p /app/backend/storage/uploads /app/backend/data/raw \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/backend

# Spaces routes public traffic to this port (see app_port in the Space README).
EXPOSE 7860

CMD ["uvicorn", "api_app.app:app", "--host", "0.0.0.0", "--port", "7860"]
