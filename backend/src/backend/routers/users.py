"""
Admin user roster: list, delete, and promote/demote.

Deleting an admin is deliberately harder than deleting a regular user: it
needs an explicit `?confirm=true` (the frontend gates this behind a
stronger, type-the-email confirmation rather than a plain window.confirm).

An admin can never delete their own account, full stop - this is also what
keeps the system from ever reaching zero admins without a separate "last
admin" count check: every DELETE is made by *some* admin, so if the caller
is deleting a *different* admin, at least two admins existed going in and at
least the caller remains after. Demotion has no such free lunch (an admin
demoting themselves is allowed), so update_user_role checks the admin count
directly.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from backend.db.models import ROLE_ADMIN
from backend.db.repositories import users
from backend.dependencies import AdminUser, DbSession
from backend.schemas import AdminUserResponse, UpdateUserRoleRequest

router = APIRouter()


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    session: DbSession,
    admin: AdminUser,
) -> list[AdminUserResponse]:
    return [AdminUserResponse.from_model(user) for user in users.list_all(session)]


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    user_id: uuid.UUID,
    session: DbSession,
    admin: AdminUser,
    confirm: bool = False,
) -> None:
    target = users.get_by_id(session, user_id)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )

    if target.role == ROLE_ADMIN and not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deleting an admin requires confirmation.",
        )

    users.delete(session, target)
    session.commit()


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserResponse,
)
def update_user_role(
    user_id: uuid.UUID,
    request: UpdateUserRoleRequest,
    session: DbSession,
    admin: AdminUser,
) -> AdminUserResponse:
    target = users.get_by_id(session, user_id)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    is_demotion = target.role == ROLE_ADMIN and request.role != ROLE_ADMIN

    if is_demotion and users.count_by_role(session, ROLE_ADMIN) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote the last remaining admin.",
        )

    users.set_role(session, target, request.role)
    session.commit()

    return AdminUserResponse.from_model(target)
