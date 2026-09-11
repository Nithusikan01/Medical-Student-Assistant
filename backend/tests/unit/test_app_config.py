"""
Configuration read at process start.

Both of these are deployment-critical and invisible until production: a
mis-parsed CORS list silently breaks every browser request, and a weak or
missing SECRET_KEY silently weakens every token.
"""

import pytest

from backend.app import DEFAULT_CORS_ORIGINS, cors_origins
from backend.auth.config import (
    DEFAULT_ACCESS_TOKEN_TTL_MINUTES,
    MIN_SECRET_KEY_LENGTH,
    load_auth_config,
)

VALID_KEY = "x" * MIN_SECRET_KEY_LENGTH


# ----------------------------------------------------------------------
# CORS
# ----------------------------------------------------------------------


def test_cors_falls_back_to_local_development(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert cors_origins() == list(DEFAULT_CORS_ORIGINS)


def test_an_empty_cors_variable_falls_back_too(monkeypatch):
    """
    An unset variable and one set to "" must behave the same, or a blank
    value in a deployment dashboard would lock every browser out.
    """

    monkeypatch.setenv("CORS_ORIGINS", "   ")

    assert cors_origins() == list(DEFAULT_CORS_ORIGINS)


def test_cors_origins_are_split_and_trimmed(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        " https://app.example.com , https://staging.example.com ",
    )

    assert cors_origins() == [
        "https://app.example.com",
        "https://staging.example.com",
    ]


def test_a_trailing_slash_is_removed(monkeypatch):
    """
    Browsers send the Origin header without a trailing slash, so
    "https://app.example.com/" would never match and every request would be
    blocked.
    """

    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com/")

    assert cors_origins() == ["https://app.example.com"]


# ----------------------------------------------------------------------
# Auth configuration
# ----------------------------------------------------------------------


def test_a_missing_secret_key_fails_fast(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValueError):
        load_auth_config()


def test_a_short_secret_key_fails_fast(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "too-short")

    with pytest.raises(ValueError):
        load_auth_config()


def test_defaults_are_applied(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", VALID_KEY)

    for name in (
        "ACCESS_TOKEN_TTL_MINUTES",
        "ALLOW_OPEN_REGISTRATION",
        "COOKIE_SECURE",
        "ADMIN_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_auth_config()

    assert config.access_token_ttl_minutes == DEFAULT_ACCESS_TOKEN_TTL_MINUTES
    assert config.admin_email is None

    # Both default closed: an operator has to opt in to open registration
    # and, in production, to insecure cookies.
    assert config.allow_open_registration is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("maybe", False),
    ],
)
def test_boolean_variables_accept_the_usual_spellings(monkeypatch, raw, expected):
    monkeypatch.setenv("SECRET_KEY", VALID_KEY)
    monkeypatch.setenv("COOKIE_SECURE", raw)

    assert load_auth_config().cookie_secure is expected


def test_blank_optional_strings_become_none(monkeypatch):
    """
    An empty ADMIN_EMAIL must read as "not configured" rather than as an
    account with an empty address.
    """

    monkeypatch.setenv("SECRET_KEY", VALID_KEY)
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")

    config = load_auth_config()

    assert config.admin_email is None
    assert config.google_client_id is None
