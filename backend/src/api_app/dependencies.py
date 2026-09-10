import uuid
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from rag_application.config.settings import load_settings
from sqlalchemy.orm import Session

from api_app.auth.config import AuthConfig, load_auth_config
from api_app.auth.exceptions import InvalidTokenError
from api_app.auth.service import AuthService
from api_app.auth.tokens import decode_access_token
from api_app.db.models import User
from api_app.db.repositories import users
from api_app.db.session import get_db

# auto_error=False so a missing header produces our own 401 shape rather than
# FastAPI's, and so optional-auth routes stay possible later.
bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache
def get_settings():
    return load_settings()


@lru_cache
def get_auth_config() -> AuthConfig:
    return load_auth_config()


def get_rag_service(request: Request):
    return request.app.state.rag_service


def get_auth_service(
    session: Annotated[Session, Depends(get_db)],
    config: Annotated[AuthConfig, Depends(get_auth_config)],
) -> AuthService:
    return AuthService(session, config)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db)],
    config: Annotated[AuthConfig, Depends(get_auth_config)],
) -> User:
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(config, credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = users.get_by_id(session, user_id)

    # The token can outlive the account being deleted or disabled, so the row
    # is authoritative rather than the claims.
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION

    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required.",
        )

    return user


RagService = Annotated[Any, Depends(get_rag_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]
Auth = Annotated[AuthService, Depends(get_auth_service)]
Config = Annotated[AuthConfig, Depends(get_auth_config)]
