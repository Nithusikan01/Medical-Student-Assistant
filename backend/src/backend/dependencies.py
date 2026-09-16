import uuid
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from rag.config.settings import load_settings
from rag.observability import Tracer
from sqlalchemy.orm import Session

from backend.auth.config import AuthConfig, load_auth_config
from backend.auth.exceptions import InvalidTokenError
from backend.auth.service import AuthService
from backend.auth.tokens import decode_access_token
from backend.db.models import User
from backend.db.repositories import users
from backend.db.session import get_db
from backend.wiring.rag_factory import (
    DEFAULT_GENERATION_MODEL_ID,
    GenerationModelOption,
    all_generation_models,
    available_generation_models,
    build_tracer,
    resolve_generator,
)

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


def get_tracer(request: Request) -> Tracer:
    """
    The process-wide tracer.

    Read off app.state when the lifespan has run, so tests that build the
    app without it still get a working (no-op) tracer rather than an
    AttributeError.
    """

    tracer = getattr(request.app.state, "tracer", None)

    return tracer if tracer is not None else build_tracer()


def get_generation_models() -> list[GenerationModelOption]:
    return available_generation_models()


def get_all_generation_models() -> list[GenerationModelOption]:
    return all_generation_models()


def get_default_generation_model_id() -> str:
    return DEFAULT_GENERATION_MODEL_ID


def get_generator_resolver():
    """
    Returns resolve_generator itself, not a call to it - the model id to
    resolve is only known once the request body is parsed. Going through
    Depends (rather than the router importing rag_factory directly) is what
    lets API tests override this with a stub instead of needing real
    provider credentials.
    """

    return resolve_generator


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
Telemetry = Annotated[Tracer, Depends(get_tracer)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_db)]
Auth = Annotated[AuthService, Depends(get_auth_service)]
Config = Annotated[AuthConfig, Depends(get_auth_config)]
GenerationModels = Annotated[
    list[GenerationModelOption], Depends(get_generation_models)
]
AllGenerationModels = Annotated[
    list[GenerationModelOption], Depends(get_all_generation_models)
]
DefaultGenerationModelId = Annotated[str, Depends(get_default_generation_model_id)]
GeneratorResolver = Annotated[Any, Depends(get_generator_resolver)]
