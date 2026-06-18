from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from rag_application.api.routers.health import router as health_router
from rag_application.api.routers.query import router as query_router

load_dotenv(
    dotenv_path=Path(__file__).resolve().parents[3] / ".env"
)


def create_app() -> FastAPI:

    app = FastAPI(
        title="RAG Application API",
        description="API for the RAG Application",
        version="1.0.0"
    )

    app.include_router(
        health_router,
        prefix="/health",
        tags=["Health"]
    )

    app.include_router(
        query_router,
        prefix="/api",
        tags=["Query"]
    )

    return app

app = create_app()