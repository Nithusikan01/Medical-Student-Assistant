import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api_app.db.base import Base

if TYPE_CHECKING:
    from api_app.db.models.user import User

PROVIDER_GOOGLE = "google"


class OAuthAccount(Base):
    """
    A federated credential linked to a local user.

    Identity lives in `users`; this table only records which external
    accounts may sign in as that user, so adding a second provider later
    is a data change rather than a schema change.
    """

    __tablename__ = "oauth_accounts"

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

    provider: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # Google's `sub` claim: stable even when the user changes their address.
    provider_account_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    provider_email: Mapped[str | None] = mapped_column(sa.String(320))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")

    __table_args__ = (
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_oauth_accounts_provider_account",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_oauth_accounts_user_provider",
        ),
        sa.Index("ix_oauth_accounts_user_id", "user_id"),
    )
