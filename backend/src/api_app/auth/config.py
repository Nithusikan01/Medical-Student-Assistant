import os
from dataclasses import dataclass

DEFAULT_ACCESS_TOKEN_TTL_MINUTES = 15
DEFAULT_REFRESH_TOKEN_TTL_DAYS = 30
MIN_SECRET_KEY_LENGTH = 32


@dataclass(frozen=True)
class AuthConfig:
    secret_key: str
    access_token_ttl_minutes: int = DEFAULT_ACCESS_TOKEN_TTL_MINUTES
    refresh_token_ttl_days: int = DEFAULT_REFRESH_TOKEN_TTL_DAYS
    algorithm: str = "HS256"
    google_client_id: str | None = None
    allow_open_registration: bool = False
    admin_email: str | None = None
    admin_password: str | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_auth_config() -> AuthConfig:
    secret_key = os.getenv("SECRET_KEY")

    if not secret_key:
        raise ValueError("SECRET_KEY environment variable is not set.")

    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ValueError(
            "SECRET_KEY must be at least " f"{MIN_SECRET_KEY_LENGTH} characters long."
        )

    return AuthConfig(
        secret_key=secret_key,
        access_token_ttl_minutes=int(
            os.getenv(
                "ACCESS_TOKEN_TTL_MINUTES",
                str(DEFAULT_ACCESS_TOKEN_TTL_MINUTES),
            )
        ),
        refresh_token_ttl_days=int(
            os.getenv(
                "REFRESH_TOKEN_TTL_DAYS",
                str(DEFAULT_REFRESH_TOKEN_TTL_DAYS),
            )
        ),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        allow_open_registration=_env_bool("ALLOW_OPEN_REGISTRATION", False),
        admin_email=os.getenv("ADMIN_EMAIL") or None,
        admin_password=os.getenv("ADMIN_PASSWORD") or None,
    )
