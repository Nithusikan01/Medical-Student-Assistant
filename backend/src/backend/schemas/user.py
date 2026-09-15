import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class UpdateUserRoleRequest(BaseModel):
    role: Literal["user", "admin"]


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, user) -> "AdminUserResponse":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )
