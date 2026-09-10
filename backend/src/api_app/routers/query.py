import logging

from fastapi import APIRouter, HTTPException, status

from api_app.db.repositories import conversations
from api_app.dependencies import CurrentUser, DbSession, RagService
from api_app.schemas import (
    QueryRequest,
    QueryResponse,
    SourceChunk,
    SourceMetadata,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
)
def query_documents(
    request: QueryRequest,
    session: DbSession,
    user: CurrentUser,
    rag_service: RagService,
) -> QueryResponse:

    conversation = conversations.get(session, request.conversation_id)

    if conversation is None:
        conversation = conversations.create(
            session,
            conversation_id=request.conversation_id,
            user_id=user.id,
            title=conversations.derive_title(request.question),
        )
        session.commit()
    elif conversation.user_id != user.id:
        # Reported as missing rather than forbidden, so the response cannot be
        # used to discover which conversation ids exist.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    try:
        answer, chunks = rag_service.answer_with_sources(
            conversation_id=str(request.conversation_id),
            question=request.question,
            top_k=request.top_k,
        )
    except Exception as exc:
        # The underlying message can carry Pinecone or Gemini detail,
        # including credentials embedded in URLs, so it stays in the log.
        logger.exception("Query failed for conversation %s.", conversation.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant could not answer that right now.",
        ) from exc

    sources = [
        SourceChunk(
            id=chunk.id,
            score=getattr(chunk, "score", 0.0),
            retrieval_method=getattr(chunk, "retrieval_method", None),
            rerank_score=getattr(chunk, "rerank_score", None),
            text=chunk.text,
            preview=chunk.text[:250],
            metadata=SourceMetadata(
                document_id=chunk.metadata.document_id,
                filename=chunk.metadata.filename,
                page_number=chunk.metadata.page_number,
                section_title=chunk.metadata.section_title,
                heading_level=chunk.metadata.heading_level,
                chunk_index=chunk.metadata.chunk_index,
            ),
        )
        for chunk in chunks
    ]

    if sources:
        conversations.attach_sources_to_latest_answer(
            session,
            conversation.id,
            [source.model_dump(mode="json") for source in sources],
        )

    if conversation.title is None:
        conversation.title = conversations.derive_title(request.question)

    session.commit()

    return QueryResponse(
        conversation_id=str(conversation.id),
        question=request.question,
        answer=answer,
        sources=sources,
    )
