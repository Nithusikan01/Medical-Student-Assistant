import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rag.utils.logger import setup_logging

from backend.auth.bootstrap import ensure_admin_user
from backend.db.session import get_engine, get_session_factory, session_scope
from backend.db.startup import verify_connectivity, warn_if_schema_outdated
from backend.dependencies import get_auth_config
from backend.observability.middleware import TelemetryMiddleware
from backend.routers.auth import router as auth_router
from backend.routers.conversations import router as conversations_router
from backend.routers.documents import router as documents_router
from backend.routers.health import router as health_router
from backend.routers.ingest import router as ingest_router
from backend.routers.monitoring import router as monitoring_router
from backend.routers.query import router as query_router
from backend.routers.usage import router as usage_router
from backend.routers.users import router as users_router
from backend.services.ingest_recovery import recover_on_startup
from backend.wiring.rag_factory import (
    build_history_aware_rag_service,
    build_telemetry_sink,
    build_tracer,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Initialize logging once when the application starts
setup_logging()

logger = logging.getLogger(__name__)


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

    # A process killed mid-ingest leaves its document stuck in "processing"
    # for good: nothing raised, so nothing marked it failed. This is the
    # replacement process, so this is the moment to reconcile.
    recover_on_startup(get_session_factory())

    app.state.rag_service = build_history_aware_rag_service()

    # Telemetry is started last and guarded on both ends: the application
    # must boot, and must shut down, whether or not monitoring works.
    app.state.tracer = build_tracer()
    telemetry_sink = build_telemetry_sink()

    if telemetry_sink is not None:
        try:
            telemetry_sink.start()
        except Exception:
            logger.exception("Could not start the telemetry writer.")

    try:
        yield
    finally:
        if telemetry_sink is not None:
            try:
                telemetry_sink.stop()
            except Exception:
                logger.exception("Could not stop the telemetry writer cleanly.")


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
    # Added before CORS so that CORS ends up the outer of the two: a
    # preflight is then answered without ever reaching telemetry, and a
    # browser can read the trace id because CORS exposes it explicitly.
    app.add_middleware(TelemetryMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Without this the browser hides both headers from application
        # code, and a user could not quote the id of a bad answer.
        expose_headers=["X-Trace-ID", "X-Request-ID"],
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

    app.include_router(
        usage_router,
        prefix="/api",
        tags=["Usage"],
    )

    app.include_router(
        monitoring_router,
        prefix="/api",
        tags=["Monitoring"],
    )

    return app


app = create_app()
