from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from rag_application.api.schemas import IngestRequest, IngestResponse
from rag_application.config.settings import load_settings
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.vectorstore.pinecone_store import PineconeVectorStore

router = APIRouter()


@lru_cache()
def get_ingestion_pipeline():
    settings = load_settings()

    embedder = Embedder(settings.embedding_config())
    dimension = len(embedder.model.encode("dimension_check"))

    return IngestionPipeline(
        document_loader=DocumentLoader(),
        chunker=TextChunker(settings.chunking_config()),
        embedder=embedder,
        vector_data_processor=VectorDataProcessor(),
        vector_store=PineconeVectorStore(
            settings=settings,
            dimension=dimension,
        ),
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest_document(request: IngestRequest) -> IngestResponse:

    file_path = Path(request.file_path).expanduser()

    if not file_path.exists():
        raise HTTPException(404, f"File not found: {file_path}")

    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(400, "Only PDF ingestion supported.")

    try:
        pipeline = get_ingestion_pipeline()
        pipeline.run(file_path)

        return IngestResponse(
            file_path=str(file_path),
            status="success",
            message="Document ingested successfully."
        )

    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc