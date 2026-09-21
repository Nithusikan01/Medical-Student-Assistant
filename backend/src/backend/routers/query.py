import logging
import time

from fastapi import APIRouter, HTTPException, status
from rag.llm.metering import collect_usage

from backend.db.repositories import conversations
from backend.db.repositories import usage as usage_repo
from backend.dependencies import (
    CurrentTrace,
    CurrentUser,
    DbSession,
    DefaultGenerationModelId,
    GenerationModels,
    GeneratorResolver,
    RagService,
)
from backend.schemas import (
    GenerationModelInfo,
    GenerationModelsResponse,
    QueryRequest,
    QueryResponse,
    SourceChunk,
    SourceMetadata,
)
from backend.wiring.rag_factory import UnknownGenerationModelError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/models",
    response_model=GenerationModelsResponse,
)
def list_generation_models(
    user: CurrentUser,
    models: GenerationModels,
    default_model_id: DefaultGenerationModelId,
) -> GenerationModelsResponse:
    return GenerationModelsResponse(
        models=[
            GenerationModelInfo(id=model.id, label=model.label, provider=model.provider)
            for model in models
        ],
        default=default_model_id,
    )


@router.post(
    "/query",
    response_model=QueryResponse,
)
def query_documents(
    request: QueryRequest,
    session: DbSession,
    user: CurrentUser,
    rag_service: RagService,
    resolve_generator: GeneratorResolver,
    models: GenerationModels,
    trace: CurrentTrace,
) -> QueryResponse:

    started_at = time.perf_counter()

    try:
        generator, resolved_model = resolve_generator(request.model)
    except UnknownGenerationModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or unavailable generation model: {exc}",
        ) from exc

    resolved_provider = next(
        (model.provider for model in models if model.id == resolved_model),
        "unknown",
    )

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

    trace.set_conversation(str(conversation.id))

    # Every LLM call the request makes is metered, not just the final
    # answer: query rewriting runs on every question, summarisation every
    # twelve messages, and the Gemini reranker whenever hosted reranking
    # fails. Counting only generation understated real spend by ~10%.
    try:
        with collect_usage() as usage:
            answer, chunks = rag_service.answer_with_sources(
                conversation_id=str(request.conversation_id),
                question=request.question,
                top_k=request.top_k,
                generator=generator,
                # The service is handed a generator, not its catalog id,
                # and the response cache must not serve one model's answer
                # as another's - so the id travels with it.
                model_id=resolved_model,
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

    # Written after the answer is safely in hand: accounting must never be
    # the reason a successful answer fails to reach the user.
    usage_repo.record_collected(
        session,
        events=usage.events,
        default_model_id=resolved_model,
        default_provider=resolved_provider,
        trace_id=trace.trace_id,
        user_id=user.id,
    )

    session.commit()

    # Declared on the response model (and mirrored in the frontend types)
    # since the schema was written, but never populated until now.
    processing_time_ms = int((time.perf_counter() - started_at) * 1000)

    trace.set(
        model=resolved_model,
        provider=resolved_provider,
        top_k=request.top_k,
        source_count=len(sources),
        processing_time_ms=processing_time_ms,
        llm_calls=len(usage.events),
        total_tokens=usage.total_tokens,
    )

    return QueryResponse(
        conversation_id=str(conversation.id),
        question=request.question,
        answer=answer,
        model=resolved_model,
        sources=sources,
        processing_time_ms=processing_time_ms,
        message_id=conversations.latest_answer_id(session, conversation.id),
    )
