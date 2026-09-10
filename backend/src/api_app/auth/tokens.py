import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from api_app.auth.config import AuthConfig
from api_app.auth.exceptions import InvalidTokenError

ACCESS_TOKEN_TYPE = "access"

REFRESH_TOKEN_BYTES = 48


def create_access_token(
    config: AuthConfig,
    *,
    user_id: uuid.UUID | str,
    email: str,
    role: str,
) -> str:
    issued_at = datetime.now(UTC)

    expires_at = issued_at + timedelta(minutes=config.access_token_ttl_minutes)

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }

    return jwt.encode(
        payload,
        config.secret_key,
        algorithm=config.algorithm,
    )


def decode_access_token(
    config: AuthConfig,
    token: str,
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            config.secret_key,
            algorithms=[config.algorithm],
        )
    except JWTError as exc:
        raise InvalidTokenError("Access token is invalid or expired.") from exc

    # A refresh token must never be accepted as an access token.
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("Token is not an access token.")

    if not payload.get("sub"):
        raise InvalidTokenError("Access token has no subject.")

    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """
    Refresh tokens are stored only as a digest, so a database leak does not
    hand out usable sessions. A plain sha256 is right here: the token is
    high-entropy random, so it needs no slow KDF.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry(config: AuthConfig) -> datetime:
    return datetime.now(UTC) + timedelta(days=config.refresh_token_ttl_days)
