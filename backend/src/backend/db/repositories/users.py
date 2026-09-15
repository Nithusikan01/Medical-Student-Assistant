import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import ROLE_USER, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def list_all(session: Session) -> list[User]:
    return list(session.scalars(sa.select(User).order_by(User.created_at.desc())))


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(sa.select(User).where(User.email == normalize_email(email)))


def get_by_email_for_update(session: Session, email: str) -> User | None:
    """
    Lock the row so concurrent OAuth logins cannot both decide to provision.

    SQLite ignores FOR UPDATE, so the unique constraints remain the real
    guarantee; this only narrows the window on Postgres.
    """

    return session.scalar(
        sa.select(User).where(User.email == normalize_email(email)).with_for_update()
    )


def create(
    session: Session,
    *,
    email: str,
    password_hash: str | None = None,
    full_name: str | None = None,
    role: str = ROLE_USER,
    email_verified: bool = False,
    is_active: bool = True,
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=password_hash,
        full_name=full_name,
        role=role,
        email_verified=email_verified,
        is_active=is_active,
    )

    session.add(user)
    session.flush()

    return user


def count_by_role(session: Session, role: str) -> int:
    return session.scalar(
        sa.select(sa.func.count()).select_from(User).where(User.role == role)
    )


def set_role(session: Session, user: User, role: str) -> User:
    user.role = role
    session.flush()

    return user


def delete(session: Session, user: User) -> None:
    # users.id cascades to conversations/refresh_tokens/oauth_accounts and
    # SET NULLs documents.uploaded_by (see the FK ondelete on each model).
    session.delete(user)
