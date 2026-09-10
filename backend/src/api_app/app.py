from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_app.routers.health import router as health_router
from api_app.routers.ingest import router as ingest_router
from api_app.routers.query import router as query_router
from api_app.wiring.rag_factory import build_history_aware_rag_service
from rag_application.utils.logger import setup_logging

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Initialize logging once when the application starts
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle.
    """
    app.state.rag_service = build_history_aware_rag_service()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG Application API",
        description="Hybrid + Rerank + Memory-aware RAG API",
        version="2.0.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS Configuration
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # React (Vite)
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # API Routers
    # ------------------------------------------------------------------
    app.include_router(
        health_router,
        prefix="/health",
        tags=["Health"],
    )

    app.include_router(
        ingest_router,
        prefix="/api",
        tags=["Ingestion"],
    )

    app.include_router(
        query_router,
        prefix="/api",
        tags=["Query"],
    )

    return app


app = create_app()