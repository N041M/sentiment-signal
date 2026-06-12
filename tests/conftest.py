"""Pytest fixtures.

DB tests run against a real PostgreSQL test database (not SQLite): the ORM models
use pgvector Vector(768), JSONB, UUID, and ARRAY, none of which compile on SQLite.
The fixture auto-creates a dedicated `<db>_test` database, enables pgvector, and
wraps each test in a transaction that is rolled back afterwards.

If PostgreSQL is unavailable (or the role lacks CREATEDB), DB tests skip cleanly —
pure-function tests (test_signal.py, test_resolve.py) do not use these fixtures and
always run.

Override the target with TEST_DATABASE_URL, e.g.:
    TEST_DATABASE_URL=postgresql://sentiment:sentiment@localhost:5432/sentiment_signal_test
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import sentiment_signal.db.models  # noqa: F401  — registers all models on Base.metadata
from sentiment_signal.config import settings
from sentiment_signal.db.session import Base


def _test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(settings.database_url)
    return str(url.set(database=f"{url.database}_test"))


def _ensure_test_db(url: str) -> None:
    """Best-effort create the test database via the 'postgres' maintenance DB."""
    u = make_url(url)
    admin_engine = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": u.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{u.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def db_engine():
    url = _test_database_url()
    try:
        _ensure_test_db(url)
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(engine)
    except Exception as exc:  # Postgres down, no pgvector, or no CREATEDB right
        pytest.skip(f"PostgreSQL test database unavailable ({url}): {exc}")
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Transactional session — each test runs in a transaction rolled back at teardown."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    try:
        yield session
    finally:
        session.close()
        # A test that triggered an IntegrityError has already rolled the transaction
        # back, so only roll back if it is still active (avoids a SAWarning).
        if transaction.is_active:
            transaction.rollback()
        connection.close()
