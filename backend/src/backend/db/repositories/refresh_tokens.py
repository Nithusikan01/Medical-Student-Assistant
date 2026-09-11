import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import RefreshToken


def create(
    session: Session,
    *,
    user_id: uuid.UUID,
    token_hash: str,
    family_id: uuid.UUID,
    expires_at: datetime,
    user_agent: str | None = None,
    ip: str | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
        user_agent=user_agent,
        ip=ip,
    )

    session.add(token)
    session.flush()

    return token


def get_by_hash(session: Session, token_hash: str) -> RefreshToken | None:
    return session.scalar(
        sa.select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )


def revoke(
    session: Session,
    token: RefreshToken,
    *,
    at: datetime,
    replaced_by_id: uuid.UUID | None = None,
) -> None:
    token.revoked_at = at
    token.replaced_by_id = replaced_by_id


def revoke_family(
    session: Session,
    family_id: uuid.UUID,
    *,
    at: datetime,
) -> int:
    """
    Kill every live token descended from one login.

    Called when an already-revoked token is presented: that means someone is
    replaying a stolen token, so the whole chain is untrustworthy.
    """

    result = session.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=at)
    )

    return result.rowcount or 0


def revoke_all_for_user(
    session: Session,
    user_id: uuid.UUID,
    *,
    at: datetime,
) -> int:
    result = session.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=at)
    )

    return result.rowcount or 0
