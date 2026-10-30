"""Test configuration.

Tests run against a dedicated PostgreSQL database (TEST_DATABASE_URL) migrated with Alembic so the
database-level immutability trigger and partial unique indexes are exercised exactly as in the app.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)

_storage = tempfile.mkdtemp(prefix="controliq-test-evidence-")
os.environ["EVIDENCE_STORAGE_DIR"] = _storage
os.environ["OPENAI_API_KEY"] = ""

from app.core.config import get_settings  # noqa: E402

_base = get_settings()
TEST_URL = os.environ.get("TEST_DATABASE_URL") or _base.test_database_url
if not TEST_URL:
    raise RuntimeError("TEST_DATABASE_URL must be configured to run the test suite")
if TEST_URL == _base.database_url:
    raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL; the test database is wiped")
os.environ["DATABASE_URL"] = TEST_URL
get_settings.cache_clear()

from sqlalchemy import text  # noqa: E402

from app.core import database  # noqa: E402

database.configure_engine(TEST_URL)

from app.core.database import Base, SessionLocal  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from tests import factory  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    from alembic import command
    from alembic.config import Config

    with database.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")
    yield
    database.engine.dispose()
    shutil.rmtree(_storage, ignore_errors=True)


def _wipe():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text("SET LOCAL controliq.allow_purge = 'on'"))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    for f in Path(_storage).iterdir():
        f.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clean_state():
    _wipe()
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = True


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def world(db):
    """A small but complete synthetic environment (users, services, assets, dependencies, controls)."""
    return factory.build_world(db)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(email: str):
        client.cookies.clear()
        r = client.post(
            "/api/v1/auth/login", json={"email": email, "password": get_settings().demo_password}
        )
        assert r.status_code == 200, r.text
        return client

    return _login
