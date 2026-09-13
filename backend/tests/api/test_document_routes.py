"""
Admin document management.

The shared corpus is the product's single source of truth, so these routes
are admin-only and their effects are deliberately narrow: the router decides
who may act and whether the document exists, and delegates the actual
removal to DocumentService (covered in tests/unit/test_document_service.py).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.db.models import STATUS_FAILED, STATUS_READY, Document


@pytest.fixture
def stored_document(db, admin):
    def _store(filename="pharmacology.pdf", status=STATUS_READY, uploaded_by=...):
        document = Document(
            id=uuid.uuid4(),
            filename=filename,
            status=status,
            chunk_count=12,
            page_count=4,
            uploaded_by=admin.id if uploaded_by is ... else uploaded_by,
        )

        db.add(document)
        db.commit()

        return document.id

    return _store


def test_listing_shows_documents_with_their_uploader(
    client: TestClient, admin, auth_headers, stored_document
):
    stored_document()

    response = client.get("/api/documents", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()

    assert len(body) == 1
    assert body[0]["filename"] == "pharmacology.pdf"
    assert body[0]["status"] == STATUS_READY
    assert body[0]["chunk_count"] == 12
    assert body[0]["uploaded_by_email"] == admin.email


def test_listing_is_empty_before_anything_is_uploaded(
    client: TestClient, admin, auth_headers
):
    assert client.get("/api/documents", headers=auth_headers(admin)).json() == []


def test_listing_survives_a_deleted_uploader(
    client: TestClient, admin, auth_headers, stored_document
):
    """
    uploaded_by is ON DELETE SET NULL, so a removed admin must not make the
    whole list 500.
    """

    stored_document(uploaded_by=None)

    response = client.get("/api/documents", headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()[0]["uploaded_by_email"] is None


def test_a_failed_document_is_still_listed(
    client: TestClient, admin, auth_headers, stored_document
):
    """Otherwise a broken upload would be invisible and undeletable."""

    stored_document(status=STATUS_FAILED)

    body = client.get("/api/documents", headers=auth_headers(admin)).json()

    assert body[0]["status"] == STATUS_FAILED


def test_deleting_a_document_delegates_to_the_service(
    client: TestClient, admin, auth_headers, stored_document, document_service
):
    document_id = stored_document()

    response = client.delete(
        f"/api/documents/{document_id}",
        headers=auth_headers(admin),
    )

    assert response.status_code == 204
    assert document_service.deleted == [document_id]


def test_deleting_an_unknown_document_is_a_404(
    client: TestClient, admin, auth_headers, document_service
):
    response = client.delete(
        f"/api/documents/{uuid.uuid4()}",
        headers=auth_headers(admin),
    )

    assert response.status_code == 404
    assert document_service.deleted == []


def test_a_failed_deletion_is_reported_as_a_bad_gateway(
    client: TestClient, admin, auth_headers, stored_document, monkeypatch
):
    """
    The vector store is an upstream dependency, so its failure is a 502 and
    not a 500: the request was valid and retrying is the right response.
    """

    from backend.services.document_service import DocumentDeletionError

    document_id = stored_document()

    class FailingService:
        def delete(self, _document_id):
            raise DocumentDeletionError("The document's vectors could not be removed.")

    monkeypatch.setattr(
        "backend.routers.documents.get_document_service",
        lambda: FailingService(),
    )

    response = client.delete(
        f"/api/documents/{document_id}",
        headers=auth_headers(admin),
    )

    assert response.status_code == 502


def test_purging_reports_how_many_vectors_went(
    client: TestClient, admin, auth_headers, stored_document, document_service
):
    document_id = stored_document()

    response = client.post(
        f"/api/documents/{document_id}/purge",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json() == {"vectors_removed": 0}
    assert document_service.purged == [document_id]


def test_ingest_rejects_a_non_pdf_upload(client: TestClient, admin, auth_headers):
    response = client.post(
        "/api/ingest",
        headers=auth_headers(admin),
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
