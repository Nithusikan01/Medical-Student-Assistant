from functools import lru_cache

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api_app.schemas import IngestResponse
from api_app.services.upload_service import UploadService
from api_app.wiring.rag_factory import build_history_aware_rag_service
from rag_application.config.settings import load_settings
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.vectorstore.pinecone_store import PineconeVectorStore

router = APIRouter()


@lru_cache()
def get_ingestion_pipeline() -> IngestionPipeline:
    settings = load_settings()

    embedder = Embedder(
        settings.embedding_config()
    )

    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=embedder.dimension,
    )

    return IngestionPipeline(
        loader=DocumentLoader(),
        chunker=TextChunker(
            settings.chunking_config()
        ),
        embedder=embedder,
        processor=VectorDataProcessor(),
        vector_store=vector_store,
        batch_size=settings.embedding_batch_size,
        bm25_corpus_path=settings.bm25_corpus_path,
    )


@lru_cache()
def get_upload_service() -> UploadService:
    return UploadService()


@router.post(
    "/ingest",
    response_model=IngestResponse,
)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
) -> IngestResponse:

    if (
        file.content_type != "application/pdf"
        and not (file.filename or "").lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported.",
        )

    upload_service = get_upload_service()

    saved_file = upload_service.save(file)

    try:
        pipeline = get_ingestion_pipeline()

        pipeline.ingest(saved_file)
        build_history_aware_rag_service.cache_clear()
        request.app.state.rag_service = build_history_aware_rag_service()

        return IngestResponse(
            filename=file.filename or saved_file.name,
            status="success",
            message="Document ingested successfully.",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    finally:
        upload_service.delete(saved_file)
