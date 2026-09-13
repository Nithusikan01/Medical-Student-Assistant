import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from backend.auth.config import AuthConfig
from backend.auth.exceptions import InvalidTokenError
from backend.auth.tokens import (
    ACCESS_TOKEN_TYPE,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from tests.conftest import TEST_SECRET_KEY


@pytest.fixture
def config() -> AuthConfig:
    return AuthConfig(secret_key=TEST_SECRET_KEY)


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def test_access_token_round_trip(config, user_id):
    token = create_access_token(
        config,
        user_id=user_id,
        email="student@example.com",
        role="user",
    )

    payload = decode_access_token(config, token)

    assert payload["sub"] == str(user_id)
    assert payload["email"] == "student@example.com"
    assert payload["role"] == "user"
    assert payload["type"] == ACCESS_TOKEN_TYPE


def test_each_token_has_a_unique_id(config, user_id):
    """The jti is what a future revocation list would key on."""

    first = decode_access_token(
        config,
        create_access_token(config, user_id=user_id, email="a@b.co", role="user"),
    )
    second = decode_access_token(
        config,
        create_access_token(config, user_id=user_id, email="a@b.co", role="user"),
    )

    assert first["jti"] != second["jti"]


def test_token_signed_with_another_key_is_rejected(config, user_id):
    other = AuthConfig(secret_key="a-completely-different-secret-key-xx")

    token = create_access_token(
        other,
        user_id=user_id,
        email="student@example.com",
        role="user",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(config, token)


def test_tampered_token_is_rejected(config, user_id):
    token = create_access_token(
        config,
        user_id=user_id,
        email="student@example.com",
        role="user",
    )

    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"

    with pytest.raises(InvalidTokenError):
        decode_access_token(config, tampered)


def test_expired_token_is_rejected(user_id):
    expired = AuthConfig(
        secret_key=TEST_SECRET_KEY,
        access_token_ttl_minutes=-1,
    )

    token = create_access_token(
        expired,
        user_id=user_id,
        email="student@example.com",
        role="user",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired, token)


def test_a_refresh_typed_token_is_not_accepted_as_an_access_token(config, user_id):
    """
    Both token kinds would verify against the same secret, so the type claim
    is the only thing stopping a long-lived refresh token from being used as
    a bearer token.
    """

    forged = jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        config.secret_key,
        algorithm=config.algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(config, forged)


def test_a_token_without_a_subject_is_rejected(config):
    subjectless = jwt.encode(
        {
            "type": ACCESS_TOKEN_TYPE,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
        config.secret_key,
        algorithm=config.algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(config, subjectless)


def test_refresh_tokens_are_unique():
    tokens = {generate_refresh_token() for _ in range(100)}

    assert len(tokens) == 100


def test_refresh_token_hash_is_deterministic_and_not_the_token():
    raw = generate_refresh_token()

    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw
    assert len(hash_refresh_token(raw)) == 64


def test_refresh_expiry_honours_the_configured_lifetime():
    config = AuthConfig(secret_key=TEST_SECRET_KEY, refresh_token_ttl_days=7)

    expiry = refresh_token_expiry(config)

    assert expiry.tzinfo is not None
    assert timedelta(days=6, hours=23) < expiry - datetime.now(UTC)
    assert expiry - datetime.now(UTC) <= timedelta(days=7)
