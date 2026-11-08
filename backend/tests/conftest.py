"""Shared pytest fixtures.

Phase 0/1 use an in-memory SQLite engine (StaticPool, shared across threads) so
the default ``pytest`` run needs no Postgres and no API key. Integration tests
(Postgres checkpointer, pgvector) will opt in later and use a separate fixture.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_agent_runtime() -> Generator[None, None, None]:
    """Reset the agent runner's checkpointer/LLM between tests."""
    yield
    from app.agents.common import runner

    runner.configure_runtime(checkpointer=None, llm_factory=None)
