import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

API_ROOT = Path(__file__).resolve().parents[1]

os.environ["POSTGRES_HOST"] = os.getenv("TEST_POSTGRES_HOST", "localhost")
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "supplyhub_test")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "supplyhub")
os.environ["POSTGRES_PASSWORD"] = os.getenv(
    "TEST_POSTGRES_PASSWORD",
    "supplyhub_test_password",
)

from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture(scope="session")
def migrated_database() -> None:
    database_name = os.environ["POSTGRES_DB"]

    if not database_name.endswith("_test"):
        raise RuntimeError("Tests require a database whose name ends with '_test'")

    alembic_config = Config(API_ROOT / "alembic.ini")
    command.upgrade(alembic_config, "head")


@pytest.fixture
def db_session(migrated_database: None) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()

    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
