from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI

from rag_application.api.routers.health import router as health_router
from rag_application.api.routers.ingest import router as ingest_router
from rag_application.api.routers.query import router as query_router
from rag_application.wiring.rag_factory import build_history_aware_rag_service


load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def create_app() -> FastAPI:

    app = FastAPI(
        title="RAG Application API",
        description="Hybrid + Rerank + Memory-aware RAG API",
        version="2.0.0"
    )

    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(ingest_router, prefix="/api", tags=["Ingestion"])
    app.include_router(query_router, prefix="/api", tags=["Query"])

    @app.on_event("startup")
    def startup_event():
        app.state.rag_service = build_history_aware_rag_service()

    return app


app = create_app()