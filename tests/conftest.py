"""
Shared pytest fixtures.

Design decision: tests run against a real PostgreSQL instance (the same
one docker-compose spins up), not SQLite or a mocked database. Several
schema decisions from Phase 4 -- CHECK constraints, jsonb columns -- are
PostgreSQL-specific and would silently behave differently (or not be
enforced at all) under SQLite. A test suite that passes against SQLite
but doesn't actually exercise the real constraints would be a false
positive, which is worse than no test at all.

This means: tests require DATABASE_URL to point at a reachable Postgres
(either the docker-compose 'db' service or a local Postgres instance).
The GitHub Actions workflow (.github/workflows/ci.yml) provides this via
a Postgres service container.
"""

import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db

# Load .env so TEST_DATABASE_URL comes from the same file as everything
# else, rather than requiring it to be typed inline on every pytest
# invocation. python-dotenv does NOT override variables already set in
# the shell, so an explicit `TEST_DATABASE_URL=... pytest` still wins if
# you ever need to point at a different database temporarily.
load_dotenv()

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://atlas:atlas@localhost:5432/atlas_test",
)


@pytest.fixture(scope="session")
def engine():
    """One engine for the whole test session -- avoids reconnect overhead per test."""
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """
    Fresh session per test, wrapped in a transaction that's rolled back
    at the end -- keeps tests isolated from each other without needing
    to manually clean up rows after every test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """
    FastAPI TestClient with the get_db dependency overridden to use the
    same rolled-back-after-test session as db_session above, so test
    assertions against the DB and assertions against the API see the
    same data.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True, scope="session")
def _verify_test_db_reachable(engine):
    """
    Fails fast with a clear message if Postgres isn't reachable, instead
    of letting every single test fail with a cryptic connection error.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.exit(
            f"Cannot reach test database at {TEST_DATABASE_URL}. "
            f"Is Postgres running? Original error: {exc}"
        )
