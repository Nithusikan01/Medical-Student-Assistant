import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag.utils.logger import setup_logging

from backend.auth.bootstrap import ensure_admin_user
from backend.db.session import get_engine, session_scope
from backend.db.startup import verify_connectivity, warn_if_schema_outdated
from backend.dependencies import get_auth_config
from backend.routers.auth import router as auth_router
from backend.routers.conversations import router as conversations_router
from backend.routers.documents import router as documents_router
from backend.routers.health import router as health_router
from backend.routers.ingest import router as ingest_router
from backend.routers.query import router as query_router
from backend.routers.users import router as users_router
from backend.wiring.rag_factory import build_history_aware_rag_service

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Initialize logging once when the application starts
setup_logging()


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "")

    origins = [
        origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()
    ]

    return origins or list(DEFAULT_CORS_ORIGINS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle.
    """
    engine = get_engine()

    verify_connectivity(engine)
    warn_if_schema_outdated(engine)

    with session_scope() as session:
        ensure_admin_user(session, get_auth_config())

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
    #
    # Origins come from CORS_ORIGINS (comma separated) so a deployment can
    # name its own frontend. Credentials are allowed, which forbids the "*"
    # wildcard, so every permitted origin must be listed explicitly.
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
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
        auth_router,
        prefix="/api",
        tags=["Authentication"],
    )

    app.include_router(
        conversations_router,
        prefix="/api",
        tags=["Conversations"],
    )

    app.include_router(
        ingest_router,
        prefix="/api",
        tags=["Ingestion"],
    )

    app.include_router(
        documents_router,
        prefix="/api",
        tags=["Documents"],
    )

    app.include_router(
        query_router,
        prefix="/api",
        tags=["Query"],
    )

    app.include_router(
        users_router,
        prefix="/api",
        tags=["Users"],
    )

    return app


app = create_app()
