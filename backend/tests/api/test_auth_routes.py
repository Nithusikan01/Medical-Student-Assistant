"""
The auth endpoints, exercised through HTTP.

The refresh cookie is the part worth testing at this level rather than in the
service: its flags are what stop a stolen token from being read by JavaScript
or sent to the wrong path, and none of that is visible from AuthService.
"""

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from backend.db.models import User
from backend.routers.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from tests.conftest import KNOWN_PASSWORD

NEW_PASSWORD = "a-brand-new-password"

REGISTRATION = {
    "email": "student@example.com",
    "password": NEW_PASSWORD,
    "full_name": "A Student",
}


def refresh_cookie_attributes(response) -> dict[str, str]:
    """
    httpx drops cookie attributes, so the raw Set-Cookie header is the only
    place the flags can be checked.
    """

    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{REFRESH_COOKIE_NAME}="):
            parts = [part.strip() for part in header.split(";")]

            # Starlette clears a cookie by setting it to a quoted empty
            # string, so the quotes are stripped for comparability.
            attributes = {"value": parts[0].split("=", 1)[1].strip('"')}

            for part in parts[1:]:
                key, _, value = part.partition("=")
                attributes[key.lower()] = value

            return attributes

    raise AssertionError("no refresh cookie was set")


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


def test_register_returns_an_access_token_and_the_user(client: TestClient):
    response = client.post("/api/auth/register", json=REGISTRATION)

    assert response.status_code == 201
    body = response.json()

    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "student@example.com"
    assert body["user"]["role"] == "user"
    assert body["user"]["has_password"] is True
    assert body["user"]["has_google"] is False


def test_register_never_returns_the_password_hash(client: TestClient):
    response = client.post("/api/auth/register", json=REGISTRATION)

    assert "password" not in response.text.lower().replace('"has_password"', "")


def test_register_sets_an_http_only_refresh_cookie(client: TestClient):
    response = client.post("/api/auth/register", json=REGISTRATION)

    cookie = refresh_cookie_attributes(response)

    assert cookie["value"]
    assert "httponly" in cookie, "script-readable refresh tokens defeat the design"
    assert cookie["samesite"].lower() == "lax"
    assert (
        cookie["path"] == REFRESH_COOKIE_PATH
    ), "a broader path would attach the refresh token to every API call"


def test_the_refresh_cookie_is_not_the_access_token(client: TestClient):
    response = client.post("/api/auth/register", json=REGISTRATION)

    assert (
        refresh_cookie_attributes(response)["value"] != response.json()["access_token"]
    )


def test_register_rejects_a_duplicate_email(client: TestClient):
    client.post("/api/auth/register", json=REGISTRATION)

    response = client.post("/api/auth/register", json=REGISTRATION)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": NEW_PASSWORD},
        {"email": "student@example.com", "password": "short"},
        {"password": NEW_PASSWORD},
        {"email": "student@example.com"},
    ],
    ids=["bad-email", "short-password", "no-email", "no-password"],
)
def test_register_validates_its_input(client: TestClient, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


@pytest.mark.closed_registration
def test_register_is_refused_without_an_invite_when_registration_is_closed(
    client: TestClient,
):
    response = client.post("/api/auth/register", json=REGISTRATION)

    assert response.status_code == 403


# ----------------------------------------------------------------------
# Login
# ----------------------------------------------------------------------


def test_login_succeeds_with_the_right_password(client: TestClient, user):
    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)
    assert refresh_cookie_attributes(response)["value"]


def test_login_fails_with_the_wrong_password(client: TestClient, user):
    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "not-the-password"},
    )

    assert response.status_code == 401


def test_login_for_an_unknown_account_looks_identical(client: TestClient, user):
    known = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "not-the-password"},
    )
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password"},
    )

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_login_is_forbidden_for_a_disabled_account(client: TestClient, make_user):
    disabled = make_user("banned@example.com", is_active=False)

    response = client.post(
        "/api/auth/login",
        json={"email": disabled.email, "password": KNOWN_PASSWORD},
    )

    assert response.status_code == 403


# ----------------------------------------------------------------------
# Refresh rotation
# ----------------------------------------------------------------------


def test_refresh_without_a_cookie_is_unauthorised(client: TestClient):
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_rotates_the_cookie_and_returns_a_new_access_token(
    client: TestClient, user
):
    login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )
    first_cookie = refresh_cookie_attributes(login)["value"]

    response = client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert refresh_cookie_attributes(response)["value"] != first_cookie
    assert response.json()["user"]["id"] == str(user.id)


def test_replaying_a_rotated_cookie_is_rejected_and_clears_it(client: TestClient, user):
    login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )
    stolen = refresh_cookie_attributes(login)["value"]

    client.post("/api/auth/refresh")

    # The thief presents the token the legitimate client already rotated
    # away from.
    client.cookies.set(REFRESH_COOKIE_NAME, stolen, path=REFRESH_COOKIE_PATH)
    replay = client.post("/api/auth/refresh")

    assert replay.status_code == 401
    assert refresh_cookie_attributes(replay)["value"] == ""


def test_the_family_is_dead_after_a_replay(client: TestClient, user):
    login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )
    stolen = refresh_cookie_attributes(login)["value"]

    rotated = refresh_cookie_attributes(client.post("/api/auth/refresh"))["value"]

    client.cookies.set(REFRESH_COOKIE_NAME, stolen, path=REFRESH_COOKIE_PATH)
    client.post("/api/auth/refresh")

    client.cookies.set(REFRESH_COOKIE_NAME, rotated, path=REFRESH_COOKIE_PATH)

    # Even the legitimate client's current token is now revoked: after a
    # confirmed leak, everyone re-authenticates.
    assert client.post("/api/auth/refresh").status_code == 401


# ----------------------------------------------------------------------
# Logout
# ----------------------------------------------------------------------


def test_logout_clears_the_cookie_and_kills_the_session(client: TestClient, user):
    client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert refresh_cookie_attributes(response)["value"] == ""
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_without_a_session_still_succeeds(client: TestClient):
    """A client with a stale cookie must be able to reach a clean state."""

    assert client.post("/api/auth/logout").status_code == 204


def test_logout_all_revokes_other_sessions(client: TestClient, user, auth_headers):
    client.post(
        "/api/auth/login",
        json={"email": user.email, "password": KNOWN_PASSWORD},
    )

    response = client.post("/api/auth/logout-all", headers=auth_headers(user))

    assert response.status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401


# ----------------------------------------------------------------------
# Identity and password change
# ----------------------------------------------------------------------


def test_me_returns_the_bearer_identity(client: TestClient, user, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_a_token_for_a_deleted_account_is_rejected(
    client: TestClient, user, auth_headers, db
):
    """
    The access token stays valid for its full lifetime, so the row - not the
    claims - has to be authoritative.
    """

    headers = auth_headers(user)

    db.execute(sa.delete(User).where(User.id == user.id))
    db.commit()

    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_a_token_for_a_disabled_account_is_rejected(
    client: TestClient, user, auth_headers, db
):
    headers = auth_headers(user)

    db.get(User, user.id).is_active = False
    db.commit()

    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_changing_a_password_requires_the_current_one(
    client: TestClient, user, auth_headers
):
    response = client.post(
        "/api/auth/password",
        headers=auth_headers(user),
        json={"new_password": NEW_PASSWORD, "current_password": "wrong-password"},
    )

    assert response.status_code == 400


def test_changing_a_password_then_logging_in_with_it(
    client: TestClient, user, auth_headers
):
    response = client.post(
        "/api/auth/password",
        headers=auth_headers(user),
        json={"new_password": NEW_PASSWORD, "current_password": KNOWN_PASSWORD},
    )

    assert response.status_code == 204

    assert (
        client.post(
            "/api/auth/login",
            json={"email": user.email, "password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": user.email, "password": KNOWN_PASSWORD},
        ).status_code
        == 401
    )


def test_a_new_password_must_meet_the_length_rule(
    client: TestClient, user, auth_headers
):
    response = client.post(
        "/api/auth/password",
        headers=auth_headers(user),
        json={"new_password": "short", "current_password": KNOWN_PASSWORD},
    )

    assert response.status_code == 422
