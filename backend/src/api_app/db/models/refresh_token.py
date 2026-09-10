import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from api_app.db.base import Base


class RefreshToken(Base):
    """
    A single issued refresh token.

    Tokens are opaque and stored only as a SHA-256 hash. Every use rotates
    the token and links the old row to its replacement, so presenting an
    already-revoked token proves theft and lets the whole family be killed.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        unique=True,
    )

    family_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)

    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
    )

    user_agent: Mapped[str | None] = mapped_column(sa.String(512))

    ip: Mapped[str | None] = mapped_column(sa.String(64))

    __table_args__ = (
        sa.Index("ix_refresh_tokens_user_id", "user_id"),
        sa.Index("ix_refresh_tokens_family_id", "family_id"),
        sa.Index("ix_refresh_tokens_expires_at", "expires_at"),
    )
