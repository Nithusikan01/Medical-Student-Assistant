import logging
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def verify_connectivity(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(sa.text("SELECT 1"))

    logger.info("Database connection established.")


def warn_if_schema_outdated(engine: Engine) -> None:
    """
    Compare the applied revision against the newest one on disk.

    Logs rather than raises: refusing to boot on a mismatch would turn a
    forgotten migration into a total outage, and the operator needs the app
    up to read this message.
    """

    try:
        config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))

        head = ScriptDirectory.from_config(config).get_current_head()

        with engine.connect() as connection:
            applied = MigrationContext.configure(connection).get_current_revision()
    except Exception:
        logger.exception("Could not determine the database schema version.")
        return

    if applied == head:
        logger.info("Database schema is up to date (%s).", applied)
        return

    logger.warning(
        "Database schema is at revision %s but the code expects %s. "
        "Run 'alembic upgrade head' from the backend directory.",
        applied or "(none)",
        head,
    )
