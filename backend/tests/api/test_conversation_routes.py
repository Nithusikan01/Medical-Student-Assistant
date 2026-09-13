"""
Conversation CRUD.

The property that matters most here is isolation: one student must never be
able to read, rename, or delete another's chat, and must not be able to learn
that a given conversation id exists at all.
"""

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from backend.db.models import Conversation, ConversationMessage


@pytest.fixture
def other_user(make_user):
    return make_user("someone.else@example.com")


def create_conversation(client, user, auth_headers, title="Cardiology") -> str:
    response = client.post(
        "/api/conversations",
        headers=auth_headers(user),
        json={"title": title},
    )

    assert response.status_code == 201

    return response.json()["id"]


def test_creating_a_conversation_returns_it_empty(
    client: TestClient, user, auth_headers
):
    response = client.post(
        "/api/conversations",
        headers=auth_headers(user),
        json={"title": "Cardiology"},
    )

    body = response.json()

    assert response.status_code == 201
    assert body["title"] == "Cardiology"
    assert body["messages"] == []
    assert uuid.UUID(body["id"])


def test_a_conversation_may_be_created_untitled(client: TestClient, user, auth_headers):
    response = client.post("/api/conversations", headers=auth_headers(user), json={})

    assert response.status_code == 201
    assert response.json()["title"] is None


def test_listing_returns_only_your_own_conversations(
    client: TestClient, user, other_user, auth_headers
):
    mine = create_conversation(client, user, auth_headers, "Mine")
    create_conversation(client, other_user, auth_headers, "Theirs")

    response = client.get("/api/conversations", headers=auth_headers(user))

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [mine]


def test_listing_reports_message_counts(
    client: TestClient, user, auth_headers, session_factory, db
):
    conversation_id = create_conversation(client, user, auth_headers)

    db.add_all(
        ConversationMessage(
            conversation_id=uuid.UUID(conversation_id),
            role=role,
            content=content,
        )
        for role, content in [("user", "Q"), ("assistant", "A"), ("user", "Q2")]
    )
    db.commit()

    body = client.get("/api/conversations", headers=auth_headers(user)).json()

    assert body[0]["message_count"] == 3


def test_fetching_a_conversation_returns_its_messages_and_sources(
    client: TestClient, user, auth_headers, db
):
    conversation_id = create_conversation(client, user, auth_headers)
    sources = [{"id": "doc_chunk_0", "filename": "bnf.pdf"}]

    db.add(
        ConversationMessage(
            conversation_id=uuid.UUID(conversation_id),
            role="assistant",
            content="500 mg.",
            sources=sources,
        )
    )
    db.commit()

    body = client.get(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(user),
    ).json()

    assert [m["content"] for m in body["messages"]] == ["500 mg."]
    assert body["messages"][0]["sources"] == sources


def test_renaming_a_conversation(client: TestClient, user, auth_headers):
    conversation_id = create_conversation(client, user, auth_headers)

    response = client.patch(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(user),
        json={"title": "Renal physiology"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renal physiology"


def test_a_rename_must_not_be_blank(client: TestClient, user, auth_headers):
    conversation_id = create_conversation(client, user, auth_headers)

    response = client.patch(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(user),
        json={"title": ""},
    )

    assert response.status_code == 422


def test_deleting_a_conversation_removes_its_messages(
    client: TestClient, user, auth_headers, db
):
    conversation_id = create_conversation(client, user, auth_headers)

    db.add(
        ConversationMessage(
            conversation_id=uuid.UUID(conversation_id),
            role="user",
            content="Q",
        )
    )
    db.commit()

    response = client.delete(
        f"/api/conversations/{conversation_id}",
        headers=auth_headers(user),
    )

    assert response.status_code == 204

    db.expire_all()

    assert db.get(Conversation, uuid.UUID(conversation_id)) is None
    assert db.scalars(sa.select(ConversationMessage)).all() == []


# ----------------------------------------------------------------------
# Isolation between users
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("GET", None),
        ("PATCH", {"title": "Hijacked"}),
        ("DELETE", None),
    ],
)
def test_another_users_conversation_is_reported_as_missing(
    client: TestClient, user, other_user, auth_headers, method, payload
):
    """
    404 rather than 403 on purpose: a 403 would confirm the id exists and
    turn the endpoint into an enumeration oracle.
    """

    theirs = create_conversation(client, other_user, auth_headers)

    kwargs = {"json": payload} if payload else {}
    response = client.request(
        method,
        f"/api/conversations/{theirs}",
        headers=auth_headers(user),
        **kwargs,
    )

    assert response.status_code == 404


def test_a_missing_and_a_forbidden_conversation_are_indistinguishable(
    client: TestClient, user, other_user, auth_headers
):
    theirs = create_conversation(client, other_user, auth_headers)
    nonexistent = uuid.uuid4()

    forbidden = client.get(f"/api/conversations/{theirs}", headers=auth_headers(user))
    missing = client.get(
        f"/api/conversations/{nonexistent}", headers=auth_headers(user)
    )

    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json()


def test_a_rejected_rename_does_not_take_effect(
    client: TestClient, user, other_user, auth_headers, db
):
    theirs = create_conversation(client, other_user, auth_headers, "Theirs")

    client.patch(
        f"/api/conversations/{theirs}",
        headers=auth_headers(user),
        json={"title": "Hijacked"},
    )

    db.expire_all()

    assert db.get(Conversation, uuid.UUID(theirs)).title == "Theirs"


def test_a_malformed_conversation_id_is_a_validation_error(
    client: TestClient, user, auth_headers
):
    response = client.get("/api/conversations/not-a-uuid", headers=auth_headers(user))

    assert response.status_code == 422
