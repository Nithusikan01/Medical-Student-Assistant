"""
Admin user roster: list, delete, promote/demote.

Who may register and how is covered in tests/api/test_auth_routes.py; this
covers the admin-only listing plus the safety rules around removing or
demoting an admin - the system must never end up with zero admins, and an
admin can never delete their own account.
"""

from fastapi.testclient import TestClient

from backend.db.models import ROLE_ADMIN, User


def test_listing_shows_every_user_with_their_join_date(
    client: TestClient, admin, user, auth_headers
):
    response = client.get("/api/users", headers=auth_headers(admin))

    assert response.status_code == 200
    body = response.json()

    emails = {row["email"] for row in body}
    assert emails == {admin.email, user.email}

    admin_row = next(row for row in body if row["email"] == admin.email)
    assert admin_row["role"] == "admin"
    assert admin_row["is_active"] is True
    assert admin_row["created_at"]


def test_admin_can_delete_a_regular_user(
    client: TestClient, admin, user, auth_headers, db
):
    response = client.delete(f"/api/users/{user.id}", headers=auth_headers(admin))

    assert response.status_code == 204
    assert db.get(User, user.id) is None


def test_an_admin_can_never_delete_their_own_account(
    client: TestClient, admin, auth_headers, db
):
    """
    Unconditional, even with ?confirm=true - this is also what guarantees a
    delete can never zero out the admins: whoever is deleted, the caller
    (who is necessarily an admin) survives.
    """

    response = client.delete(
        f"/api/users/{admin.id}?confirm=true", headers=auth_headers(admin)
    )

    assert response.status_code == 400
    assert db.get(User, admin.id) is not None


def test_deleting_an_admin_without_confirmation_is_rejected(
    client: TestClient, admin, make_user, auth_headers, db
):
    other_admin = make_user("second-admin@example.com", role=ROLE_ADMIN)

    response = client.delete(
        f"/api/users/{other_admin.id}", headers=auth_headers(admin)
    )

    assert response.status_code == 400
    assert db.get(User, other_admin.id) is not None


def test_deleting_an_admin_with_confirmation_succeeds(
    client: TestClient, admin, make_user, auth_headers, db
):
    other_admin = make_user("second-admin@example.com", role=ROLE_ADMIN)

    response = client.delete(
        f"/api/users/{other_admin.id}?confirm=true", headers=auth_headers(admin)
    )

    assert response.status_code == 204
    assert db.get(User, other_admin.id) is None


def test_admin_can_promote_a_user_to_admin(
    client: TestClient, admin, user, auth_headers
):
    response = client.patch(
        f"/api/users/{user.id}/role",
        headers=auth_headers(admin),
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_demoting_the_last_admin_is_rejected(client: TestClient, admin, auth_headers):
    """
    Unlike delete, an admin demoting *themselves* is allowed, so this is the
    one place a "last admin" count check is actually reachable.
    """

    response = client.patch(
        f"/api/users/{admin.id}/role",
        headers=auth_headers(admin),
        json={"role": "user"},
    )

    assert response.status_code == 409


def test_demoting_an_admin_is_fine_when_another_admin_remains(
    client: TestClient, admin, make_user, auth_headers
):
    other_admin = make_user("second-admin@example.com", role=ROLE_ADMIN)

    response = client.patch(
        f"/api/users/{other_admin.id}/role",
        headers=auth_headers(admin),
        json={"role": "user"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"
