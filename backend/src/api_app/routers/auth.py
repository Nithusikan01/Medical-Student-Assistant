from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from api_app.auth.config import AuthConfig
from api_app.auth.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RegistrationNotAllowedError,
)
from api_app.auth.service import TokenPair
from api_app.db.models import PROVIDER_GOOGLE, User
from api_app.dependencies import Auth, Config, CurrentUser
from api_app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SetPasswordRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()

REFRESH_COOKIE_NAME = "refresh_token"

# Scoped so the browser only sends the refresh token to the endpoints that
# need it, rather than attaching it to every API call.
REFRESH_COOKIE_PATH = "/api/auth"


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        has_password=user.password_hash is not None,
        has_google=any(
            account.provider == PROVIDER_GOOGLE for account in user.oauth_accounts
        ),
    )


def _set_refresh_cookie(
    response: Response,
    tokens: TokenPair,
    config: AuthConfig,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=config.refresh_token_ttl_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
    )


def _token_response(user: User, tokens: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=_to_user_response(user),
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    auth: Auth,
    config: Config,
) -> TokenResponse:
    try:
        user = auth.register(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            invite_code=payload.invite_code,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RegistrationNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    tokens = auth.issue_tokens(
        user,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )

    _set_refresh_cookie(response, tokens, config)

    return _token_response(user, tokens)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: Auth,
    config: Config,
) -> TokenResponse:
    try:
        user = auth.authenticate(
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    tokens = auth.issue_tokens(
        user,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )

    _set_refresh_cookie(response, tokens, config)

    return _token_response(user, tokens)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    auth: Auth,
    config: Config,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token was supplied.",
        )

    try:
        user, tokens = auth.rotate_refresh_token(
            refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    except InvalidTokenError as exc:
        # The cookie is dead either way; clearing it stops the client from
        # retrying with it forever.
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except InactiveUserError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    _set_refresh_cookie(response, tokens, config)

    return _token_response(user, tokens)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: Auth,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> None:
    if refresh_token:
        auth.revoke_refresh_token(refresh_token)

    _clear_refresh_cookie(response)


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response,
    auth: Auth,
    user: CurrentUser,
) -> None:
    auth.revoke_all_sessions(user)

    _clear_refresh_cookie(response)


@router.get("/auth/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return _to_user_response(user)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    payload: SetPasswordRequest,
    auth: Auth,
    user: CurrentUser,
) -> None:
    try:
        auth.set_password(
            user,
            new_password=payload.new_password,
            current_password=payload.current_password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
