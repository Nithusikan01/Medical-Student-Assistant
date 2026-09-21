"""
Rating an answer.

The only human judgement of quality anywhere in this application. Every
other metric says how the system behaved - latency, spend, how many
chunks came back - and none of them can tell a fast, cheap,
well-retrieved wrong answer from a right one.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.db.models import AnswerFeedback, Conversation, ConversationMessage


@pytest.fixture
def conversation(db, user):
    row = Conversation(id=uuid.uuid4(), user_id=user.id, title="Cardiology")

    db.add(row)
    db.commit()

    return row


def add_message(
    db,
    conversation,
    *,
    role: str = "assistant",
    content: str = "Take 500mg.",
    trace_id: str | None = None,
    minutes_ago: float = 1.0,
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        trace_id=trace_id,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )

    db.add(message)
    db.commit()

    return message


# ----------------------------------------------------------------------
# Leaving a rating
# ----------------------------------------------------------------------


def test_an_answer_can_be_rated(client, db, user, auth_headers, conversation):
    message = add_message(db, conversation)

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up"},
    )

    assert response.status_code == 200
    assert response.json()["rating"] == "up"


def test_changing_your_mind_updates_rather_than_adds(
    client, db, user, auth_headers, conversation
):
    """One rating per answer per person, not a running tally of votes."""

    message = add_message(db, conversation)

    for rating in ("up", "down", "up"):
        client.post(
            "/api/feedback",
            headers=auth_headers(user),
            json={"message_id": message.id, "rating": rating},
        )

    rows = db.query(AnswerFeedback).all()

    assert len(rows) == 1
    assert rows[0].rating == "up"


def test_a_comment_is_stored_with_the_rating(
    client, db, user, auth_headers, conversation
):
    message = add_message(db, conversation)

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={
            "message_id": message.id,
            "rating": "down",
            "comment": "This contradicts the dosing chapter.",
        },
    )

    assert response.json()["comment"] == "This contradicts the dosing chapter."


def test_a_blank_comment_is_no_comment(client, db, user, auth_headers, conversation):
    message = add_message(db, conversation)

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up", "comment": "   "},
    )

    assert response.json()["comment"] is None


def test_an_overlong_comment_is_rejected(client, db, user, auth_headers, conversation):
    """A rating with a note, not a second chat."""

    message = add_message(db, conversation)

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up", "comment": "x" * 1001},
    )

    assert response.status_code == 422


def test_an_invented_rating_is_rejected(client, db, user, auth_headers, conversation):
    message = add_message(db, conversation)

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "excellent"},
    )

    assert response.status_code == 422


def test_the_trace_is_captured_from_the_answer(
    client, db, user, auth_headers, conversation
):
    """
    What makes a complaint actionable: the rating points at the request
    that produced the answer, so an admin can open its waterfall.
    """

    message = add_message(db, conversation, trace_id="abc123")

    client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "down"},
    )

    assert db.query(AnswerFeedback).one().trace_id == "abc123"


# ----------------------------------------------------------------------
# What cannot be rated
# ----------------------------------------------------------------------


def test_someone_elses_answer_reads_as_missing(
    client, db, make_user, auth_headers, conversation
):
    """
    404 rather than 403, so the response cannot be used to discover which
    message ids exist - the same rule the conversation routes follow.
    """

    message = add_message(db, conversation)
    intruder = make_user(email="someone-else@example.com")

    response = client.post(
        "/api/feedback",
        headers=auth_headers(intruder),
        json={"message_id": message.id, "rating": "up"},
    )

    assert response.status_code == 404
    assert db.query(AnswerFeedback).count() == 0


def test_a_question_cannot_be_rated(client, db, user, auth_headers, conversation):
    """A trace explains an answer; a user's own question is not something
    the system produced."""

    message = add_message(db, conversation, role="user", content="What dose?")

    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up"},
    )

    assert response.status_code == 404


def test_an_unknown_message_reads_as_missing(client, user, auth_headers):
    response = client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": 999999, "rating": "up"},
    )

    assert response.status_code == 404


def test_an_anonymous_request_is_rejected(client):
    response = client.post("/api/feedback", json={"message_id": 1, "rating": "up"})

    assert response.status_code == 401


# ----------------------------------------------------------------------
# Withdrawing
# ----------------------------------------------------------------------


def test_a_rating_can_be_withdrawn(client, db, user, auth_headers, conversation):
    message = add_message(db, conversation)

    client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up"},
    )

    response = client.delete(f"/api/feedback/{message.id}", headers=auth_headers(user))

    assert response.status_code == 204
    assert db.query(AnswerFeedback).count() == 0


def test_withdrawing_a_rating_that_is_not_there_succeeds(client, user, auth_headers):
    """Idempotent: the caller wanted no rating to exist, and none does."""

    response = client.delete("/api/feedback/999999", headers=auth_headers(user))

    assert response.status_code == 204


def test_withdrawing_cannot_reach_someone_elses_rating(
    client, db, user, make_user, auth_headers, conversation
):
    message = add_message(db, conversation)

    client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "up"},
    )

    intruder = make_user(email="not-yours@example.com")

    client.delete(f"/api/feedback/{message.id}", headers=auth_headers(intruder))

    assert db.query(AnswerFeedback).count() == 1


# ----------------------------------------------------------------------
# Replaying a conversation
# ----------------------------------------------------------------------


def test_reopening_a_conversation_shows_your_own_rating(
    client, db, user, auth_headers, conversation
):
    message = add_message(db, conversation)

    client.post(
        "/api/feedback",
        headers=auth_headers(user),
        json={"message_id": message.id, "rating": "down"},
    )

    body = client.get(
        f"/api/conversations/{conversation.id}",
        headers=auth_headers(user),
    ).json()

    assert body["messages"][0]["feedback"] == "down"


def test_an_unrated_answer_comes_back_null(
    client, db, user, auth_headers, conversation
):
    add_message(db, conversation)

    body = client.get(
        f"/api/conversations/{conversation.id}",
        headers=auth_headers(user),
    ).json()

    assert body["messages"][0]["feedback"] is None
