"""
Shared fixtures for the backend suite.

Everything here runs against a throwaway SQLite file, so the whole suite is
hermetic: no Postgres, no Pinecone, no Gemini, no network. The models were
written with portable types for exactly this reason (see db/models).
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from rag.llm.metering import UsageEvent, current_collector
from rag.llm.schemas import TokenUsage
from rag.observability import Tracer
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import create_app
from backend.auth.config import AuthConfig
from backend.auth.password import hash_password
from backend.auth.tokens import create_access_token
from backend.db.base import Base
from backend.db.models import ROLE_ADMIN, ROLE_USER, User
from backend.db.session import get_db
from backend.dependencies import (
    get_all_generation_models,
    get_auth_config,
    get_default_generation_model_id,
    get_generation_models,
    get_generator_resolver,
    get_rag_service,
)
from backend.wiring.rag_factory import (
    GenerationModelOption,
    UnknownGenerationModelError,
)

# Long enough to satisfy AuthConfig's minimum; obviously not a real key.
TEST_SECRET_KEY = "test-secret-key-not-used-anywhere-real"

KNOWN_PASSWORD = "correct-horse-battery-staple"


class _AwareDateTime(sqlite.DATETIME):
    """
    Give SQLite the timezone-aware reads Postgres already returns.

    SQLite has no datetime type, so it hands back naive values, and code that
    compares a stored expiry against `datetime.now(UTC)` would raise
    TypeError here while working fine in production. Normalising on read
    keeps the tests faithful to the real dialect instead of forcing the
    application to work around a test-only quirk.
    """

    def result_processor(self, dialect, coltype):
        inner = super().result_processor(dialect, coltype)

        def process(value):
            parsed = inner(value)

            if parsed is not None and parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)

            return parsed

        return process


@pytest.fixture
def engine(tmp_path) -> Iterator[Engine]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")

    engine.dialect.colspecs = {
        **engine.dialect.colspecs,
        sa.DateTime: _AwareDateTime,
    }

    # SQLite ignores foreign keys unless asked, which would silently hide
    # the ON DELETE CASCADE behaviour the deletion paths rely on.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session for arranging and asserting directly, outside the API."""

    session = session_factory()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def known_password_hash() -> str:
    """
    Hashed once for the whole session.

    bcrypt is deliberately slow, so hashing per test would dominate the
    suite's runtime for no added coverage.
    """

    return hash_password(KNOWN_PASSWORD)


@pytest.fixture
def auth_config(request: pytest.FixtureRequest) -> AuthConfig:
    closed = request.node.get_closest_marker("closed_registration") is not None

    return AuthConfig(
        secret_key=TEST_SECRET_KEY,
        allow_open_registration=not closed,
    )


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------

UserFactory = Callable[..., User]


@pytest.fixture
def make_user(
    session_factory: sessionmaker[Session],
    known_password_hash: str,
) -> UserFactory:
    def _make(
        email: str = "student@example.com",
        *,
        role: str = ROLE_USER,
        is_active: bool = True,
        password_hash: str | None = "",
        full_name: str | None = None,
    ) -> User:
        with session_factory() as session:
            user = User(
                email=email.lower(),
                # "" is the sentinel for "give me the known password";
                # None means a provider-only account with no password.
                password_hash=(
                    known_password_hash if password_hash == "" else password_hash
                ),
                full_name=full_name,
                role=role,
                is_active=is_active,
            )

            session.add(user)
            session.commit()
            session.refresh(user)

            return user

    return _make


@pytest.fixture
def user(make_user: UserFactory) -> User:
    return make_user("student@example.com")


@pytest.fixture
def admin(make_user: UserFactory) -> User:
    return make_user("admin@example.com", role=ROLE_ADMIN)


@pytest.fixture
def token_for(auth_config: AuthConfig) -> Callable[[User], str]:
    def _token(user: User) -> str:
        return create_access_token(
            auth_config,
            user_id=user.id,
            email=user.email,
            role=user.role,
        )

    return _token


@pytest.fixture
def auth_headers(token_for) -> Callable[[User], dict[str, str]]:
    def _headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(user)}"}

    return _headers


# ----------------------------------------------------------------------
# The application
# ----------------------------------------------------------------------


class StubRagService:
    """
    Stands in for HistoryAwareRAGService.

    The query router's contract with the engine is exactly one method, so
    the API tests can assert routing, ownership, and error masking without
    any model weights or network calls.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.answer = "Paracetamol is an analgesic."
        self.sources: list = []
        self.error: Exception | None = None
        self.usage: TokenUsage | None = None

    def answer_with_sources(self, *, conversation_id, question, top_k, generator=None):
        self.calls.append(
            {
                "conversation_id": conversation_id,
                "question": question,
                "top_k": top_k,
                "generator": generator,
            }
        )

        if self.error is not None:
            raise self.error

        # Stands in for the metered generator the real service would call.
        # Usage now reaches the router through the ambient collector rather
        # than a callback, so the stub has to speak the same way.
        if self.usage is not None:
            collector = current_collector()

            if collector is not None:
                collector.record(
                    UsageEvent(
                        stage="generation",
                        usage=self.usage,
                        model="stub-model",
                        provider="stub",
                    )
                )

        return self.answer, self.sources


# Generation-model resolution is stubbed the same way as the RAG engine
# itself: real resolution needs GEMINI_API_KEY/GROQ_API_KEY, which the
# hermetic suite deliberately never sets.
STUB_DEFAULT_MODEL_ID = "stub-default"
STUB_ALT_MODEL_ID = "stub-alt"
STUB_GENERATION_MODELS = [
    GenerationModelOption(
        id=STUB_DEFAULT_MODEL_ID, label="Stub Default", provider="stub"
    ),
    GenerationModelOption(id=STUB_ALT_MODEL_ID, label="Stub Alt", provider="stub"),
]


def _stub_resolve_generator(model_id: str | None):
    resolved = model_id or STUB_DEFAULT_MODEL_ID

    if resolved not in {model.id for model in STUB_GENERATION_MODELS}:
        raise UnknownGenerationModelError(resolved)

    return object(), resolved


class StubDocumentService:
    def __init__(self) -> None:
        self.deleted: list[uuid.UUID] = []
        self.purged: list[uuid.UUID] = []

    def delete(self, document_id: uuid.UUID) -> None:
        self.deleted.append(document_id)

    def purge(self, document_id: uuid.UUID) -> int:
        self.purged.append(document_id)
        return 0


@pytest.fixture
def rag_service() -> StubRagService:
    return StubRagService()


@pytest.fixture
def generation_model_ids() -> tuple[str, str]:
    """(default id, an alternate id) as wired up by the `client` fixture."""

    return STUB_DEFAULT_MODEL_ID, STUB_ALT_MODEL_ID


@pytest.fixture
def document_service(monkeypatch: pytest.MonkeyPatch) -> StubDocumentService:
    """
    The documents router reaches for its service directly rather than
    through Depends, so it is patched at the module it is used from.
    """

    stub = StubDocumentService()

    monkeypatch.setattr(
        "backend.routers.documents.get_document_service",
        lambda: stub,
    )

    return stub


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    auth_config: AuthConfig,
    rag_service: StubRagService,
    document_service: StubDocumentService,
) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        session = session_factory()

        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_auth_config] = lambda: auth_config
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    app.dependency_overrides[get_generation_models] = lambda: STUB_GENERATION_MODELS
    app.dependency_overrides[get_all_generation_models] = lambda: STUB_GENERATION_MODELS
    app.dependency_overrides[get_default_generation_model_id] = (
        lambda: STUB_DEFAULT_MODEL_ID
    )
    app.dependency_overrides[get_generator_resolver] = lambda: _stub_resolve_generator

    # A no-op tracer, installed the way the lifespan installs the real one.
    # Without it the middleware would fall back to the factory, which reads
    # the developer's .env and would build a sink against the real database.
    app.state.tracer = Tracer()

    # Deliberately not used as a context manager: entering it would run the
    # lifespan, which connects to the real database and builds the real RAG
    # service.
    yield TestClient(app)

    app.dependency_overrides.clear()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(UTC)
