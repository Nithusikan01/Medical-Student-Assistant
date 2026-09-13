import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.db.models.oauth_account import OAuthAccount

ROLE_USER = "user"
ROLE_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        sa.String(320),
        nullable=False,
        unique=True,
    )

    # NULL means the account can only sign in through an OAuth provider.
    password_hash: Mapped[str | None] = mapped_column(sa.String(255))

    full_name: Mapped[str | None] = mapped_column(sa.String(255))

    role: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default=ROLE_USER,
        server_default=ROLE_USER,
    )

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )

    email_verified: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.CheckConstraint(
            f"role IN ('{ROLE_USER}', '{ROLE_ADMIN}')",
            name="role_valid",
        ),
        # Guards against case-variant duplicates even if a write path forgets
        # to normalize the address.
        sa.Index(
            "ix_users_email_lower",
            sa.text("lower(email)"),
            unique=True,
        ),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN
