import pytest

from backend.auth.password import (
    MAX_PASSWORD_BYTES,
    burn_password_comparison,
    hash_password,
    verify_password,
)


def test_hash_and_verify_round_trip():
    digest = hash_password("a-perfectly-fine-password")

    assert digest != "a-perfectly-fine-password"
    assert verify_password("a-perfectly-fine-password", digest)


def test_wrong_password_is_rejected():
    digest = hash_password("a-perfectly-fine-password")

    assert not verify_password("a-perfectly-fine-passwore", digest)


def test_hashing_the_same_password_twice_gives_different_digests():
    """Each hash carries its own salt, so identical passwords are not
    recognisable as identical from the stored rows."""

    first = hash_password("a-perfectly-fine-password")
    second = hash_password("a-perfectly-fine-password")

    assert first != second
    assert verify_password("a-perfectly-fine-password", first)
    assert verify_password("a-perfectly-fine-password", second)


def test_overlong_password_is_refused_rather_than_truncated():
    """
    bcrypt ignores everything past 72 bytes. Accepting a longer password
    would make it interchangeable with its own 72-byte prefix, so a user who
    set a 200-character passphrase could be let in by the first 72 bytes of
    it.
    """

    with pytest.raises(ValueError):
        hash_password("x" * (MAX_PASSWORD_BYTES + 1))


def test_verifying_an_overlong_password_fails_closed():
    digest = hash_password("x" * MAX_PASSWORD_BYTES)

    assert not verify_password("x" * (MAX_PASSWORD_BYTES + 1), digest)


def test_multibyte_password_is_measured_in_bytes():
    """A 40-character password can still exceed 72 bytes in UTF-8."""

    password = "é" * 40  # 80 bytes

    assert len(password) < MAX_PASSWORD_BYTES
    assert len(password.encode("utf-8")) > MAX_PASSWORD_BYTES

    with pytest.raises(ValueError):
        hash_password(password)


@pytest.mark.parametrize(
    "stored",
    ["", "not-a-bcrypt-hash", "$2b$12$tooshort"],
)
def test_malformed_stored_hash_returns_false(stored):
    """
    A corrupted or legacy row must fail the login, not raise a 500 that
    reveals the row is broken.
    """

    assert not verify_password("any-password-at-all", stored)


def test_burn_password_comparison_is_callable_and_silent():
    """
    Called on the no-such-user path so a missing account costs the same as a
    wrong password. It must never raise, or the timing defence would turn
    into a 500 that leaks the same information.
    """

    assert burn_password_comparison() is None
