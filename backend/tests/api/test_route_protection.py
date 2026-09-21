"""
Every /api route must be deliberately classified as public, authenticated,
or admin-only.

This is the test that catches a *future* router wired up without its
dependency: the classification is compared against the routes the app
actually exposes, so adding an endpoint without listing it here fails the
build rather than quietly shipping an open door.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

# (method, path) exactly as FastAPI reports them.
PUBLIC = {
    ("GET", "/health/health"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    # Logout is public on purpose: it acts on the refresh cookie, and an
    # expired access token must not stop a client from clearing its session.
    ("POST", "/api/auth/logout"),
}

AUTHENTICATED = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout-all"),
    ("POST", "/api/auth/password"),
    ("GET", "/api/conversations"),
    ("POST", "/api/conversations"),
    ("GET", "/api/conversations/{conversation_id}"),
    ("PATCH", "/api/conversations/{conversation_id}"),
    ("DELETE", "/api/conversations/{conversation_id}"),
    ("POST", "/api/query"),
    ("GET", "/api/models"),
    # Rating an answer is the reader's own act; ownership is checked
    # against the conversation, and someone else's message reads as 404.
    ("POST", "/api/feedback"),
    ("DELETE", "/api/feedback/{message_id}"),
}

ADMIN_ONLY = {
    ("POST", "/api/ingest"),
    ("GET", "/api/documents"),
    ("DELETE", "/api/documents/{document_id}"),
    ("POST", "/api/documents/{document_id}/purge"),
    ("GET", "/api/users"),
    ("DELETE", "/api/users/{user_id}"),
    ("PATCH", "/api/users/{user_id}/role"),
    ("GET", "/api/usage/models"),
    # Monitoring exposes every user's traffic, conversation ids and spend,
    # so it is admin-only in its entirety - there is no per-user view of it.
    ("GET", "/api/monitoring/overview"),
    ("GET", "/api/monitoring/performance"),
    ("GET", "/api/monitoring/tokens"),
    ("GET", "/api/monitoring/retrieval"),
    ("GET", "/api/monitoring/errors"),
    ("GET", "/api/monitoring/ingestion"),
    ("GET", "/api/monitoring/feedback"),
    ("GET", "/api/monitoring/alerts"),
    ("GET", "/api/monitoring/traces"),
    ("GET", "/api/monitoring/traces/{trace_id}"),
}

# Bodies that satisfy each route's schema, so a rejection is about
# authorization rather than validation.
BODIES: dict[str, dict] = {
    "/api/auth/password": {"new_password": "a-long-enough-password"},
    "/api/conversations": {"title": "Cardiology"},
    "/api/conversations/{conversation_id}": {"title": "Renamed"},
    "/api/users/{user_id}/role": {"role": "admin"},
    "/api/query": {
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "question": "What is the dose?",
    },
}

SAMPLE_ID = str(uuid.uuid4())


def _documented_routes() -> set[tuple[str, str]]:
    app = create_app()

    found = set()

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)

        if not methods or not path.startswith(("/api", "/health")):
            continue

        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue

            found.add((method, path))

    return found


def _call(client: TestClient, method: str, path: str, **kwargs):
    concrete = (
        path.replace("{conversation_id}", SAMPLE_ID)
        .replace("{document_id}", SAMPLE_ID)
        .replace("{user_id}", SAMPLE_ID)
    )

    body = BODIES.get(path)

    if body is not None and method in {"POST", "PATCH", "PUT"}:
        kwargs["json"] = body

    return client.request(method, concrete, **kwargs)


def test_every_api_route_is_classified():
    """
    Fails when a route is added without deciding who may call it.
    """

    assert _documented_routes() == PUBLIC | AUTHENTICATED | ADMIN_ONLY


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(AUTHENTICATED | ADMIN_ONLY),
)
def test_protected_route_rejects_anonymous(client: TestClient, method, path):
    response = _call(client, method, path)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(AUTHENTICATED | ADMIN_ONLY),
)
def test_protected_route_rejects_a_malformed_token(client: TestClient, method, path):
    response = _call(
        client,
        method,
        path,
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401, response.text


@pytest.mark.parametrize(("method", "path"), sorted(ADMIN_ONLY))
def test_admin_route_rejects_a_regular_user(
    client: TestClient, auth_headers, user, method, path
):
    response = _call(client, method, path, headers=auth_headers(user))

    assert response.status_code == 403, response.text


@pytest.mark.parametrize(("method", "path"), sorted(ADMIN_ONLY))
def test_admin_route_admits_an_admin(
    client: TestClient, auth_headers, admin, method, path
):
    """
    The mirror of the test above: proves the 403 comes from the role check
    and not from the route being unreachable for everyone.
    """

    response = _call(client, method, path, headers=auth_headers(admin))

    assert response.status_code not in (401, 403), response.text


# /api/auth/refresh is public but still 401s with no cookie, which is the
# absence of a credential rather than a rejected one; it is covered in
# test_auth_routes.py instead.
PUBLIC_WITHOUT_CREDENTIALS = PUBLIC - {("POST", "/api/auth/refresh")}


@pytest.mark.parametrize(("method", "path"), sorted(PUBLIC_WITHOUT_CREDENTIALS))
def test_public_route_does_not_demand_a_token(client: TestClient, method, path):
    response = _call(client, method, path)

    assert response.status_code != 401, response.text
