import hashlib
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from rag.config.settings import load_settings
from rag.ingestion.chunker import TextChunker
from rag.ingestion.document_loader import DocumentLoader
from rag.ingestion.pipeline import IngestionPipeline
from rag.ingestion.processor import VectorDataProcessor

from backend.db.session import get_session_factory
from backend.dependencies import AdminUser, CurrentTrace
from backend.schemas.document import DocumentResponse, IngestResponse
from backend.services.document_service import (
    DocumentService,
    DuplicateDocumentError,
)
from backend.services.upload_service import UploadService
from backend.wiring.rag_factory import (
    build_embedder,
    build_tracer,
    build_vector_store,
    refresh_corpus_state,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache
def get_ingestion_pipeline() -> IngestionPipeline:
    settings = load_settings()

    return IngestionPipeline(
        loader=DocumentLoader(),
        chunker=TextChunker(settings.chunking_config()),
        embedder=build_embedder(),
        processor=VectorDataProcessor(),
        vector_store=build_vector_store(),
        batch_size=settings.embedding_batch_size,
        # The middleware has already opened a trace for this request, so the
        # pipeline's spans nest under it rather than starting a second one.
        tracer=build_tracer(),
    )


@lru_cache
def get_upload_service() -> UploadService:
    return UploadService()


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(
        session_factory=get_session_factory(),
        pipeline=get_ingestion_pipeline(),
        vector_store=build_vector_store(),
        on_corpus_change=refresh_corpus_state,
    )


# Deliberately a plain `def`: ingestion is fully synchronous and CPU-bound,
# so declaring it async would block the event loop - and every other request -
# for the whole embedding run. FastAPI runs this in a worker thread instead.
@router.post(
    "/ingest",
    response_model=IngestResponse,
)
def ingest_document(
    admin: AdminUser,
    file: Annotated[UploadFile, File()],
    trace: CurrentTrace,
) -> IngestResponse:

    if file.content_type != "application/pdf" and not (
        file.filename or ""
    ).lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    upload_service = get_upload_service()
    saved_file = upload_service.save(file)

    try:
        digest = hashlib.sha256(saved_file.read_bytes()).hexdigest()

        document = get_document_service().ingest(
            file_path=saved_file,
            filename=file.filename or saved_file.name,
            content_hash=digest,
            size_bytes=saved_file.stat().st_size,
            uploaded_by=admin.id,
        )

        # Attached after the fact because the id is minted inside the
        # service. The filename is an admin-chosen document title, not user
        # content, and without it an ingestion trace reads as an anonymous
        # slow request.
        trace.set(document_id=str(document.id), filename=document.filename)

        return IngestResponse(
            filename=document.filename,
            status="success",
            message="Document ingested successfully.",
            document=DocumentResponse.from_model(
                document,
                uploaded_by_email=admin.email,
            ),
        )

    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Ingestion failed for '%s'.", file.filename)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The document could not be ingested.",
        ) from exc

    finally:
        upload_service.delete(saved_file)
