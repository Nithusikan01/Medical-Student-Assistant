import logging

import sqlalchemy as sa

from backend.auth.bootstrap import ensure_admin_user
from backend.auth.config import AuthConfig
from backend.auth.password import verify_password
from backend.db.models import ROLE_ADMIN, ROLE_USER, User
from tests.conftest import KNOWN_PASSWORD, TEST_SECRET_KEY

ADMIN_PASSWORD = "a-seeded-admin-password"


def config(**kwargs) -> AuthConfig:
    return AuthConfig(
        secret_key=TEST_SECRET_KEY,
        admin_email=kwargs.pop("admin_email", "admin@example.com"),
        admin_password=kwargs.pop("admin_password", ADMIN_PASSWORD),
        **kwargs,
    )


def users_in(db) -> list[User]:
    return list(db.scalars(sa.select(User)))


def test_seeds_the_administrator(db):
    admin = ensure_admin_user(db, config())
    db.commit()

    assert admin is not None
    assert admin.role == ROLE_ADMIN
    assert admin.email_verified is True
    assert verify_password(ADMIN_PASSWORD, admin.password_hash)


def test_seeding_twice_creates_one_account(db):
    ensure_admin_user(db, config())
    db.commit()

    ensure_admin_user(db, config())
    db.commit()

    assert len(users_in(db)) == 1


def test_a_rotated_admin_password_is_not_reset_on_restart(db, make_user):
    """
    An operator who changes the live password and forgets to update .env
    would otherwise have it silently reverted on the next deploy.
    """

    make_user("admin@example.com", role=ROLE_ADMIN)

    ensure_admin_user(db, config(admin_password="the-stale-env-password"))
    db.commit()
    db.expire_all()

    seeded = db.scalar(sa.select(User))

    assert verify_password(KNOWN_PASSWORD, seeded.password_hash)
    assert not verify_password("the-stale-env-password", seeded.password_hash)


def test_an_existing_account_named_as_admin_is_promoted(db, make_user):
    make_user("admin@example.com", role=ROLE_USER)

    ensure_admin_user(db, config())
    db.commit()
    db.expire_all()

    assert db.scalar(sa.select(User)).role == ROLE_ADMIN


def test_nothing_is_seeded_when_the_variables_are_unset(db):
    assert ensure_admin_user(db, config(admin_email=None)) is None
    assert ensure_admin_user(db, config(admin_password=None)) is None
    assert users_in(db) == []


def test_a_short_admin_password_is_refused(db, caplog):
    """
    Fails loudly rather than seeding a weak administrator, which would be
    the single most valuable account in the system.
    """

    with caplog.at_level(logging.ERROR):
        assert ensure_admin_user(db, config(admin_password="short")) is None

    assert users_in(db) == []
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
