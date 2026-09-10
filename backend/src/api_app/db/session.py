import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def database_url() -> str:
    url = os.getenv("DATABASE_URL")

    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is not set."
        )

    return url


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        database_url(),
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Iterator[Session]:
    """
    FastAPI dependency yielding a request-scoped session.

    Callers commit explicitly; an unhandled exception rolls back.
    """

    session = get_session_factory()()

    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Session for code outside the request cycle (startup, background work).
    """

    session = get_session_factory()()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
