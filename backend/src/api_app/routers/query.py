from fastapi import APIRouter, Depends, HTTPException

from api_app.dependencies import get_rag_service
from api_app.schemas import (
    QueryRequest,
    QueryResponse,
    SourceChunk,
    SourceMetadata,
)

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
)
def query_documents(
    request: QueryRequest,
    rag_service=Depends(get_rag_service),
) -> QueryResponse:

    try:

        answer, chunks = rag_service.answer_with_sources(
            conversation_id=request.conversation_id,
            question=request.question,
            top_k=request.top_k,
        )

        sources = []

        for chunk in chunks:

            metadata = chunk.metadata

            sources.append(
                SourceChunk(
                    id=chunk.id,
                    score=getattr(chunk, "score", 0.0),
                    retrieval_method=getattr(
                        chunk,
                        "retrieval_method",
                        None,
                    ),
                    rerank_score=getattr(
                        chunk,
                        "rerank_score",
                        None,
                    ),
                    text=chunk.text,
                    preview=chunk.text[:250],
                    metadata=SourceMetadata(
                        document_id=metadata.document_id,
                        filename=metadata.filename,
                        source_path=metadata.source_path,
                        page_number=metadata.page_number,
                        section_title=metadata.section_title,
                        heading_level=metadata.heading_level,
                        chunk_index=chunk.metadata.chunk_index
                    ),
                )
            )

        return QueryResponse(
            conversation_id=request.conversation_id,
            question=request.question,
            answer=answer,
            sources=sources,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc