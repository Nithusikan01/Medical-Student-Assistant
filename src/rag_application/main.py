from fastapi import FastAPI

from rag_application.api.routers.query import router as query_router
from rag_application.wiring.rag_factory import build_history_aware_rag_service

app = FastAPI(title="RAG Application")


@app.on_event("startup")
def startup_event():
    """
    Build the RAG pipeline once at startup
    """
    app.state.rag_service = build_history_aware_rag_service()


@app.get("/health")
def health():
    return {"status": "ok"}


# register routers
app.include_router(query_router, prefix="/api")