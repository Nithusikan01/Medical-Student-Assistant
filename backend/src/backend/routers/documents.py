import uuid

from fastapi import APIRouter, HTTPException, status

from backend.db.repositories import documents
from backend.dependencies import AdminUser, DbSession
from backend.routers.ingest import get_document_service
from backend.schemas.document import DocumentResponse
from backend.services.document_service import DocumentDeletionError

router = APIRouter()


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    session: DbSession,
    admin: AdminUser,
) -> list[DocumentResponse]:
    rows = documents.list_all(session)
    emails = documents.uploader_emails(session, rows)

    return [
        DocumentResponse.from_model(
            document,
            uploaded_by_email=emails.get(document.uploaded_by),
        )
        for document in rows
    ]


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: uuid.UUID,
    session: DbSession,
    admin: AdminUser,
) -> None:
    if documents.get(session, document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        get_document_service().delete(document_id)
    except DocumentDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/documents/{document_id}/purge")
def purge_document(
    document_id: uuid.UUID,
    admin: AdminUser,
) -> dict[str, int]:
    """
    Retry a failed deletion and sweep up any stray vectors.
    """

    removed = get_document_service().purge(document_id)

    return {"vectors_removed": removed}
