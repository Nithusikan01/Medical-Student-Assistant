import logging

from sqlalchemy.orm import Session

from api_app.auth.config import AuthConfig
from api_app.auth.password import MIN_PASSWORD_LENGTH, hash_password
from api_app.db.models import ROLE_ADMIN, User
from api_app.db.repositories import users

logger = logging.getLogger(__name__)


def ensure_admin_user(
    session: Session,
    config: AuthConfig,
) -> User | None:
    """
    Create the administrator named by ADMIN_EMAIL if it does not exist.

    Idempotent, and deliberately never rewrites an existing password: an
    operator who rotates ADMIN_PASSWORD in .env would otherwise silently
    reset a live account's credentials on the next restart.
    """

    if not config.admin_email or not config.admin_password:
        logger.info(
            "ADMIN_EMAIL/ADMIN_PASSWORD are not both set; "
            "skipping administrator seeding."
        )
        return None

    if len(config.admin_password) < MIN_PASSWORD_LENGTH:
        logger.error(
            "ADMIN_PASSWORD is shorter than %d characters; "
            "refusing to seed the administrator.",
            MIN_PASSWORD_LENGTH,
        )
        return None

    existing = users.get_by_email(session, config.admin_email)

    if existing is not None:
        if existing.role != ROLE_ADMIN:
            existing.role = ROLE_ADMIN
            logger.info(
                "Promoted existing account '%s' to administrator.",
                existing.email,
            )

        return existing

    admin = users.create(
        session,
        email=config.admin_email,
        password_hash=hash_password(config.admin_password),
        role=ROLE_ADMIN,
        email_verified=True,
    )

    logger.info("Seeded administrator account '%s'.", admin.email)

    return admin
