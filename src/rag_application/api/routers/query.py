from fastapi import APIRouter, HTTPException, Depends

from rag_application.api.schemas import QueryRequest, QueryResponse, SourceChunk
from rag_application.api.dependencies import get_rag_service

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query_documents(
    request: QueryRequest,
    rag_service=Depends(get_rag_service)
) -> QueryResponse:

    try:
        answer, chunks = rag_service.answer_with_sources(
            conversation_id=request.conversation_id,
            question=request.question,
            top_k=request.top_k
        )

        sources = [
            SourceChunk(
                id=c.id,
                score=getattr(c, "score", 0.0),
                text=c.text,
                metadata=c.metadata,
                retrieval_method=getattr(c, "retrieval_method", None),
            )
            for c in chunks
        ]

        return QueryResponse(
            question=request.question,
            answer=answer,
            sources=sources if sources else None
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))