import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from api_app.db.base import Base


class InviteCode(Base):
    """
    A shared code that authorizes registration when open registration is off.
    """

    __tablename__ = "invite_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    code: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        unique=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )

    max_uses: Mapped[int | None] = mapped_column(sa.Integer)

    use_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
