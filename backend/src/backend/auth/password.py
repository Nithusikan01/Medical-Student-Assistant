from functools import lru_cache

import bcrypt

# bcrypt silently truncates anything past 72 bytes, which would make two
# different long passwords interchangeable. Reject instead of truncating.
MAX_PASSWORD_BYTES = 72

MIN_PASSWORD_LENGTH = 12

_TIMING_PROBE = b"timing-equalization"


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")

    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")

    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")

    if len(encoded) > MAX_PASSWORD_BYTES:
        return False

    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed or non-bcrypt hash in the row.
        return False


@lru_cache(maxsize=1)
def _probe_hash() -> bytes:
    return bcrypt.hashpw(_TIMING_PROBE, bcrypt.gensalt())


def burn_password_comparison() -> None:
    """
    Spend the same work a real verification would.

    Called when no user matched, so that a missing account and a wrong
    password take indistinguishable time and cannot be told apart.
    """

    bcrypt.checkpw(_TIMING_PROBE, _probe_hash())
