from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from api_app.db.models import InviteCode


def get_usable(session: Session, code: str) -> InviteCode | None:
    """
    Return the code only if it is live: not revoked, not expired, and with
    uses remaining. Locked for update so two simultaneous registrations
    cannot both consume the final use.
    """

    invite = session.scalar(
        sa.select(InviteCode).where(InviteCode.code == code.strip()).with_for_update()
    )

    if invite is None or invite.revoked_at is not None:
        return None

    now = datetime.now(UTC)

    if invite.expires_at is not None and invite.expires_at <= now:
        return None

    if invite.max_uses is not None and invite.use_count >= invite.max_uses:
        return None

    return invite


def consume(invite: InviteCode) -> None:
    invite.use_count += 1
