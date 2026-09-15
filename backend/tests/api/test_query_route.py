"""
The query endpoint.

The engine itself is stubbed: what is under test here is the routing around
it - who may ask, which conversation the question lands in, and what the
client is told when the engine fails.
"""

import uuid
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from rag.retrieval.schemas import RetrievedChunk, RetrievedChunkMetadata

from backend.db.models import Conversation

QUESTION = "What is the paracetamol dose for an adult?"


def ask(client, user, auth_headers, *, conversation_id=None, question=QUESTION, **kw):
    payload = {
        "conversation_id": str(conversation_id or uuid.uuid4()),
        "question": question,
        **kw,
    }

    return client.post("/api/query", headers=auth_headers(user), json=payload)


def make_source(chunk_id="doc_chunk_0") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text="Paracetamol 500 mg to 1 g every four to six hours.",
        score=0.91,
        metadata=RetrievedChunkMetadata(
            document_id="doc",
            filename="bnf.pdf",
            source_path="C:/srv/app/storage/uploads/9b0f-2c4a.pdf",
            chunk_index=0,
            page_number=12,
        ),
    )


def test_answering_creates_the_conversation_on_first_question(
    client: TestClient, user, auth_headers, db
):
    conversation_id = uuid.uuid4()

    response = ask(client, user, auth_headers, conversation_id=conversation_id)

    assert response.status_code == 200
    assert response.json()["answer"] == "Paracetamol is an analgesic."

    conversation = db.get(Conversation, conversation_id)

    assert conversation is not None
    assert conversation.user_id == user.id


def test_the_first_question_becomes_the_title(
    client: TestClient, user, auth_headers, db
):
    conversation_id = uuid.uuid4()

    ask(client, user, auth_headers, conversation_id=conversation_id)

    assert db.get(Conversation, conversation_id).title == QUESTION


def test_a_long_question_produces_a_truncated_title(
    client: TestClient, user, auth_headers, db
):
    conversation_id = uuid.uuid4()

    ask(
        client,
        user,
        auth_headers,
        conversation_id=conversation_id,
        question="word " * 100,
    )

    title = db.get(Conversation, conversation_id).title

    assert len(title) <= 60


def test_the_question_reaches_the_engine_with_its_conversation(
    client: TestClient, user, auth_headers, rag_service
):
    conversation_id = uuid.uuid4()

    ask(client, user, auth_headers, conversation_id=conversation_id, top_k=7)

    assert rag_service.calls == [
        {
            "conversation_id": str(conversation_id),
            "question": QUESTION,
            "top_k": 7,
            "generator": mock.ANY,
        }
    ]


def test_listing_generation_models_returns_the_configured_options(
    client: TestClient, user, auth_headers, generation_model_ids
):
    default_id, alt_id = generation_model_ids

    response = client.get("/api/models", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["default"] == default_id
    assert {model["id"] for model in body["models"]} == {default_id, alt_id}


def test_omitting_a_model_resolves_to_the_default(
    client: TestClient, user, auth_headers, generation_model_ids
):
    default_id, _ = generation_model_ids

    response = ask(client, user, auth_headers)

    assert response.json()["model"] == default_id


def test_selecting_a_model_is_used_and_echoed_back(
    client: TestClient, user, auth_headers, generation_model_ids
):
    _, alt_id = generation_model_ids

    response = ask(client, user, auth_headers, model=alt_id)

    assert response.json()["model"] == alt_id


def test_requesting_an_unknown_model_is_rejected(
    client: TestClient, user, auth_headers, rag_service
):
    response = ask(client, user, auth_headers, model="not-a-real-model")

    assert response.status_code == 400
    assert rag_service.calls == [], "the engine must not run for a rejected model"


def test_sources_are_returned_to_the_client(
    client: TestClient, user, auth_headers, rag_service
):
    rag_service.sources = [make_source()]

    body = ask(client, user, auth_headers).json()

    assert len(body["sources"]) == 1
    source = body["sources"][0]

    assert source["metadata"]["filename"] == "bnf.pdf"
    assert source["metadata"]["page_number"] == 12
    assert source["preview"]


def test_the_server_filesystem_path_is_never_disclosed(
    client: TestClient, user, auth_headers, rag_service
):
    """
    The engine's chunk metadata carries the absolute upload path; the API
    schema deliberately drops it.
    """

    rag_service.sources = [make_source()]

    body = ask(client, user, auth_headers)

    assert "source_path" not in body.text
    assert "storage/uploads" not in body.text


def test_asking_in_someone_elses_conversation_is_reported_as_missing(
    client: TestClient, user, make_user, auth_headers, rag_service
):
    other = make_user("someone.else@example.com")
    theirs = uuid.uuid4()

    ask(client, other, auth_headers, conversation_id=theirs)
    rag_service.calls.clear()

    response = ask(client, user, auth_headers, conversation_id=theirs)

    assert response.status_code == 404
    assert rag_service.calls == [], "the engine must not run for a rejected request"


def test_an_engine_failure_is_masked(
    client: TestClient, user, auth_headers, rag_service
):
    """
    Pinecone and Gemini errors can carry credentials embedded in URLs, so
    the client gets a generic message and the detail goes to the log.
    """

    rag_service.error = RuntimeError(
        "pinecone request failed for key pcsk_super_secret"
    )

    response = ask(client, user, auth_headers)

    assert response.status_code == 502
    assert "pcsk_super_secret" not in response.text
    assert "pinecone" not in response.text.lower()


def test_a_failed_answer_still_leaves_the_conversation(
    client: TestClient, user, auth_headers, rag_service, db
):
    """
    The row is created before the engine runs, so a transient outage does
    not lose the chat the student was in.
    """

    conversation_id = uuid.uuid4()
    rag_service.error = RuntimeError("gemini timed out")

    ask(client, user, auth_headers, conversation_id=conversation_id)

    assert db.get(Conversation, conversation_id) is not None


def test_a_follow_up_reuses_the_same_conversation(
    client: TestClient, user, auth_headers, db
):
    conversation_id = uuid.uuid4()

    ask(client, user, auth_headers, conversation_id=conversation_id)
    ask(
        client,
        user,
        auth_headers,
        conversation_id=conversation_id,
        question="And for children?",
    )

    assert (
        db.get(Conversation, conversation_id).title == QUESTION
    ), "the title is set once, from the opening question"


@pytest.mark.parametrize(
    "payload",
    [
        {"conversation_id": "not-a-uuid", "question": QUESTION},
        {"conversation_id": str(uuid.uuid4()), "question": ""},
        {"conversation_id": str(uuid.uuid4())},
        {"question": QUESTION},
        {"conversation_id": str(uuid.uuid4()), "question": QUESTION, "top_k": 0},
        {"conversation_id": str(uuid.uuid4()), "question": QUESTION, "top_k": 21},
    ],
    ids=[
        "bad-uuid",
        "empty-question",
        "no-question",
        "no-conversation",
        "top-k-too-small",
        "top-k-too-large",
    ],
)
def test_the_request_is_validated(client: TestClient, user, auth_headers, payload):
    response = client.post("/api/query", headers=auth_headers(user), json=payload)

    assert response.status_code == 422
