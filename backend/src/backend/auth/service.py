import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RegistrationNotAllowedError,
)
from backend.auth.password import (
    burn_password_comparison,
    hash_password,
    verify_password,
)
from backend.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from backend.db.models import User
from backend.db.repositories import invite_codes, refresh_tokens, users

GENERIC_CREDENTIALS_MESSAGE = "Incorrect email or password."


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, session: Session, config: AuthConfig) -> None:
        self.session = session
        self.config = config

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
        invite_code: str | None = None,
    ) -> User:
        invite = None

        # Open registration OR a valid invite code - either is sufficient.
        if not self.config.allow_open_registration:
            invite = (
                invite_codes.get_usable(self.session, invite_code)
                if invite_code
                else None
            )

            if invite is None:
                raise RegistrationNotAllowedError(
                    "Registration requires a valid invite code."
                )

        if users.get_by_email(self.session, email) is not None:
            raise EmailAlreadyRegisteredError(
                "An account with this email already exists."
            )

        try:
            user = users.create(
                self.session,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
            )

            if invite is not None:
                invite_codes.consume(invite)

            self.session.commit()
        except IntegrityError as exc:
            # Lost a race against a concurrent registration.
            self.session.rollback()
            raise EmailAlreadyRegisteredError(
                "An account with this email already exists."
            ) from exc

        return user

    # ------------------------------------------------------------------
    # Password login
    # ------------------------------------------------------------------

    def authenticate(self, *, email: str, password: str) -> User:
        user = users.get_by_email(self.session, email)

        # A Google-only account has no password. Report it exactly like a
        # wrong password: saying "this account uses Google" would confirm the
        # address exists.
        if user is None or user.password_hash is None:
            burn_password_comparison()
            raise InvalidCredentialsError(GENERIC_CREDENTIALS_MESSAGE)

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError(GENERIC_CREDENTIALS_MESSAGE)

        # Checked only after the password is proven, so a stranger cannot
        # discover which addresses are registered-but-disabled.
        if not user.is_active:
            raise InactiveUserError("This account is not active.")

        return user

    def set_password(
        self,
        user: User,
        *,
        new_password: str,
        current_password: str | None = None,
    ) -> None:
        # Google-only accounts may set a first password without proving an old
        # one: control was already established by the provider sign-in.
        if user.password_hash is not None and (
            current_password is None
            or not verify_password(current_password, user.password_hash)
        ):
            raise InvalidCredentialsError("Current password is incorrect.")

        user.password_hash = hash_password(new_password)
        self.session.commit()

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------

    def issue_tokens(
        self,
        user: User,
        *,
        family_id: uuid.UUID | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        raw_refresh = generate_refresh_token()

        refresh_tokens.create(
            self.session,
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id or uuid.uuid4(),
            expires_at=refresh_token_expiry(self.config),
            user_agent=user_agent,
            ip=ip,
        )

        self.session.commit()

        return TokenPair(
            access_token=create_access_token(
                self.config,
                user_id=user.id,
                email=user.email,
                role=user.role,
            ),
            refresh_token=raw_refresh,
            expires_in=self.config.access_token_ttl_minutes * 60,
        )

    def rotate_refresh_token(
        self,
        raw_token: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[User, TokenPair]:
        stored = refresh_tokens.get_by_hash(self.session, hash_refresh_token(raw_token))

        if stored is None:
            raise InvalidTokenError("Refresh token is not recognised.")

        now = datetime.now(UTC)

        # Presenting a token that was already rotated away means it leaked:
        # the legitimate holder would be using its replacement. Kill the whole
        # chain rather than just this link.
        if stored.revoked_at is not None:
            refresh_tokens.revoke_family(self.session, stored.family_id, at=now)
            self.session.commit()
            raise InvalidTokenError("Refresh token has already been used.")

        if stored.expires_at <= now:
            raise InvalidTokenError("Refresh token has expired.")

        user = users.get_by_id(self.session, stored.user_id)

        if user is None or not user.is_active:
            raise InactiveUserError("This account is not active.")

        raw_refresh = generate_refresh_token()

        replacement = refresh_tokens.create(
            self.session,
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=stored.family_id,
            expires_at=refresh_token_expiry(self.config),
            user_agent=user_agent,
            ip=ip,
        )

        refresh_tokens.revoke(
            self.session,
            stored,
            at=now,
            replaced_by_id=replacement.id,
        )

        self.session.commit()

        return user, TokenPair(
            access_token=create_access_token(
                self.config,
                user_id=user.id,
                email=user.email,
                role=user.role,
            ),
            refresh_token=raw_refresh,
            expires_in=self.config.access_token_ttl_minutes * 60,
        )

    def revoke_refresh_token(self, raw_token: str) -> None:
        stored = refresh_tokens.get_by_hash(self.session, hash_refresh_token(raw_token))

        if stored is None or stored.revoked_at is not None:
            return

        refresh_tokens.revoke(self.session, stored, at=datetime.now(UTC))
        self.session.commit()

    def revoke_all_sessions(self, user: User) -> int:
        revoked = refresh_tokens.revoke_all_for_user(
            self.session, user.id, at=datetime.now(UTC)
        )

        self.session.commit()

        return revoked
