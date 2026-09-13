import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa

from backend.auth.config import AuthConfig
from backend.auth.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RegistrationNotAllowedError,
)
from backend.auth.password import verify_password
from backend.auth.service import AuthService
from backend.auth.tokens import hash_refresh_token
from backend.db.models import InviteCode, RefreshToken, User
from tests.conftest import KNOWN_PASSWORD, TEST_SECRET_KEY, utc_now

NEW_PASSWORD = "a-brand-new-password"


def make_service(session, *, open_registration: bool) -> AuthService:
    return AuthService(
        session,
        AuthConfig(
            secret_key=TEST_SECRET_KEY,
            allow_open_registration=open_registration,
        ),
    )


@pytest.fixture
def open_service(db):
    return make_service(db, open_registration=True)


@pytest.fixture
def closed_service(db):
    return make_service(db, open_registration=False)


def add_invite(db, code="LETMEIN", **kwargs) -> InviteCode:
    invite = InviteCode(code=code, **kwargs)

    db.add(invite)
    db.commit()

    return invite


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


def test_open_registration_creates_a_user(open_service, db):
    user = open_service.register(
        email="Student@Example.COM",
        password=NEW_PASSWORD,
        full_name="A Student",
    )

    assert user.email == "student@example.com", "the address should be normalised"
    assert user.full_name == "A Student"
    assert user.role == "user", "self-registration must never mint an admin"
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert db.get(User, user.id) is not None


def test_closed_registration_without_a_code_is_refused(closed_service):
    with pytest.raises(RegistrationNotAllowedError):
        closed_service.register(email="student@example.com", password=NEW_PASSWORD)


def test_closed_registration_accepts_a_valid_invite(closed_service, db):
    add_invite(db, max_uses=2)

    user = closed_service.register(
        email="student@example.com",
        password=NEW_PASSWORD,
        invite_code="LETMEIN",
    )

    db.expire_all()

    assert user.id is not None
    assert db.scalar(sa.select(InviteCode)).use_count == 1


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("revoked", {"revoked_at": utc_now()}),
        ("expired", {"expires_at": utc_now() - timedelta(days=1)}),
        ("exhausted", {"max_uses": 1, "use_count": 1}),
    ],
)
def test_closed_registration_refuses_a_dead_invite(closed_service, db, label, kwargs):
    add_invite(db, **kwargs)

    with pytest.raises(RegistrationNotAllowedError):
        closed_service.register(
            email="student@example.com",
            password=NEW_PASSWORD,
            invite_code="LETMEIN",
        )


def test_an_unlimited_invite_is_not_exhausted(closed_service, db):
    add_invite(db, max_uses=None)

    assert closed_service.register(
        email="student@example.com",
        password=NEW_PASSWORD,
        invite_code="LETMEIN",
    )


def test_registering_a_known_email_conflicts(open_service, make_user):
    make_user("student@example.com")

    with pytest.raises(EmailAlreadyRegisteredError):
        open_service.register(email="student@example.com", password=NEW_PASSWORD)


def test_the_conflict_check_ignores_case(open_service, make_user):
    """
    Otherwise two rows could differ only by capitalisation and a login would
    non-deterministically pick one of them.
    """

    make_user("student@example.com")

    with pytest.raises(EmailAlreadyRegisteredError):
        open_service.register(email="STUDENT@example.com", password=NEW_PASSWORD)


# ----------------------------------------------------------------------
# Password login
# ----------------------------------------------------------------------


def test_authenticate_accepts_the_right_password(open_service, make_user):
    user = make_user("student@example.com")

    assert (
        open_service.authenticate(
            email="student@example.com",
            password=KNOWN_PASSWORD,
        ).id
        == user.id
    )


def test_authenticate_is_case_insensitive_on_email(open_service, make_user):
    make_user("student@example.com")

    assert open_service.authenticate(
        email="  STUDENT@Example.com ",
        password=KNOWN_PASSWORD,
    )


def test_authenticate_rejects_the_wrong_password(open_service, make_user):
    make_user("student@example.com")

    with pytest.raises(InvalidCredentialsError):
        open_service.authenticate(email="student@example.com", password="nope-nope")


def test_unknown_and_wrong_password_report_the_same_thing(open_service, make_user):
    """
    A distinguishable error would turn the login form into an account
    enumeration oracle.
    """

    make_user("student@example.com")

    with pytest.raises(InvalidCredentialsError) as wrong:
        open_service.authenticate(email="student@example.com", password="nope-nope")

    with pytest.raises(InvalidCredentialsError) as missing:
        open_service.authenticate(email="nobody@example.com", password="nope-nope")

    assert str(wrong.value) == str(missing.value)


def test_a_provider_only_account_cannot_be_password_logged_in(open_service, make_user):
    """
    Reported as bad credentials rather than "this account uses Google",
    which would confirm the address is registered.
    """

    make_user("google@example.com", password_hash=None)

    with pytest.raises(InvalidCredentialsError):
        open_service.authenticate(email="google@example.com", password=KNOWN_PASSWORD)


def test_a_disabled_account_is_refused_only_after_the_password_is_proven(
    open_service, make_user
):
    make_user("banned@example.com", is_active=False)

    with pytest.raises(InactiveUserError):
        open_service.authenticate(email="banned@example.com", password=KNOWN_PASSWORD)

    # Wrong password on a disabled account must look like any other wrong
    # password, or the response would reveal that the address exists.
    with pytest.raises(InvalidCredentialsError):
        open_service.authenticate(email="banned@example.com", password="nope-nope")


# ----------------------------------------------------------------------
# Changing a password
# ----------------------------------------------------------------------


def test_changing_a_password_requires_the_current_one(open_service, make_user):
    user = make_user("student@example.com")

    with pytest.raises(InvalidCredentialsError):
        open_service.set_password(
            user,
            new_password=NEW_PASSWORD,
            current_password="not-the-password",
        )

    with pytest.raises(InvalidCredentialsError):
        open_service.set_password(user, new_password=NEW_PASSWORD)


def test_changing_a_password_succeeds_with_the_current_one(open_service, make_user):
    user = make_user("student@example.com")

    open_service.set_password(
        user,
        new_password=NEW_PASSWORD,
        current_password=KNOWN_PASSWORD,
    )

    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(KNOWN_PASSWORD, user.password_hash)


def test_a_provider_only_account_may_set_a_first_password(open_service, make_user):
    """
    There is no old password to prove; control of the account was already
    established by the provider sign-in.
    """

    user = make_user("google@example.com", password_hash=None)

    open_service.set_password(user, new_password=NEW_PASSWORD)

    assert verify_password(NEW_PASSWORD, user.password_hash)


# ----------------------------------------------------------------------
# Refresh token rotation
# ----------------------------------------------------------------------


def stored_tokens(db) -> list[RefreshToken]:
    return list(db.scalars(sa.select(RefreshToken).order_by(RefreshToken.issued_at)))


def stored_token(db, raw: str) -> RefreshToken:
    return db.scalar(
        sa.select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw)
        )
    )


def test_issue_tokens_stores_only_a_digest(open_service, make_user, db):
    user = make_user("student@example.com")

    pair = open_service.issue_tokens(user)

    db.expire_all()
    row = db.scalar(sa.select(RefreshToken).where(RefreshToken.user_id == user.id))

    assert row.token_hash == hash_refresh_token(pair.refresh_token)
    assert row.token_hash != pair.refresh_token
    assert pair.expires_in == open_service.config.access_token_ttl_minutes * 60


def test_rotation_issues_a_new_pair_and_retires_the_old_one(
    open_service, make_user, db
):
    user = make_user("student@example.com")
    first = open_service.issue_tokens(user)

    rotated_user, second = open_service.rotate_refresh_token(first.refresh_token)

    assert rotated_user.id == user.id
    assert second.refresh_token != first.refresh_token

    db.expire_all()
    old = stored_token(db, first.refresh_token)

    assert old.revoked_at is not None
    assert old.replaced_by_id is not None


def test_rotation_keeps_the_family(open_service, make_user, db):
    user = make_user("student@example.com")
    first = open_service.issue_tokens(user)

    open_service.rotate_refresh_token(first.refresh_token)

    db.expire_all()
    families = {row.family_id for row in stored_tokens(db)}

    assert len(families) == 1, "a rotation continues one login, it is not a new one"


def test_replaying_a_rotated_token_kills_the_whole_family(open_service, make_user, db):
    """
    Presenting an already-rotated token means it leaked: the legitimate
    holder would be using its replacement. Revoking only that link would
    leave the thief's newer token alive.
    """

    user = make_user("student@example.com")
    first = open_service.issue_tokens(user)
    _, second = open_service.rotate_refresh_token(first.refresh_token)

    with pytest.raises(InvalidTokenError):
        open_service.rotate_refresh_token(first.refresh_token)

    db.expire_all()

    assert all(row.revoked_at is not None for row in stored_tokens(db))

    # The replacement is dead too, so the thief gains nothing.
    with pytest.raises(InvalidTokenError):
        open_service.rotate_refresh_token(second.refresh_token)


def test_an_unknown_refresh_token_is_rejected(open_service):
    with pytest.raises(InvalidTokenError):
        open_service.rotate_refresh_token("never-issued")


def test_an_expired_refresh_token_is_rejected(make_user, db):
    service = AuthService(
        db,
        AuthConfig(secret_key=TEST_SECRET_KEY, refresh_token_ttl_days=-1),
    )
    user = make_user("student@example.com")

    pair = service.issue_tokens(user)

    with pytest.raises(InvalidTokenError):
        service.rotate_refresh_token(pair.refresh_token)


def test_rotation_refuses_a_deactivated_account(open_service, make_user, db):
    user = make_user("student@example.com")
    pair = open_service.issue_tokens(user)

    db.get(User, user.id).is_active = False
    db.commit()

    with pytest.raises(InactiveUserError):
        open_service.rotate_refresh_token(pair.refresh_token)


def test_revoking_one_token_leaves_other_sessions_alone(open_service, make_user, db):
    user = make_user("student@example.com")
    phone = open_service.issue_tokens(user)
    laptop = open_service.issue_tokens(user)

    open_service.revoke_refresh_token(phone.refresh_token)

    with pytest.raises(InvalidTokenError):
        open_service.rotate_refresh_token(phone.refresh_token)

    assert open_service.rotate_refresh_token(laptop.refresh_token)


def test_revoking_an_unknown_token_is_silent(open_service):
    """Logout must succeed even with a stale cookie, or clients get stuck."""

    assert open_service.revoke_refresh_token("never-issued") is None


def test_logging_out_everywhere_revokes_every_live_session(open_service, make_user, db):
    user = make_user("student@example.com")
    phone = open_service.issue_tokens(user)
    laptop = open_service.issue_tokens(user)

    revoked = open_service.revoke_all_sessions(user)

    assert revoked == 2

    for pair in (phone, laptop):
        with pytest.raises(InvalidTokenError):
            open_service.rotate_refresh_token(pair.refresh_token)


def test_logging_out_everywhere_does_not_touch_another_user(open_service, make_user):
    mine = make_user("student@example.com")
    theirs = make_user("other@example.com")

    open_service.issue_tokens(mine)
    their_pair = open_service.issue_tokens(theirs)

    open_service.revoke_all_sessions(mine)

    assert open_service.rotate_refresh_token(their_pair.refresh_token)


def test_tokens_from_different_users_do_not_collide(open_service, make_user):
    a = make_user("a@example.com")
    b = make_user("b@example.com")

    assert (
        open_service.issue_tokens(a).refresh_token
        != open_service.issue_tokens(b).refresh_token
    )


def test_family_id_differs_between_separate_logins(open_service, make_user, db):
    user = make_user("student@example.com")

    open_service.issue_tokens(user)
    open_service.issue_tokens(user)

    db.expire_all()

    assert len({row.family_id for row in stored_tokens(db)}) == 2


def test_refresh_token_is_bound_to_its_user(open_service, make_user, db):
    user = make_user("student@example.com")
    pair = open_service.issue_tokens(user)

    db.expire_all()
    row = stored_token(db, pair.refresh_token)

    assert row.user_id == user.id
    assert isinstance(row.family_id, uuid.UUID)
