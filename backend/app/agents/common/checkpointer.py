"""Checkpointer factory: durable Postgres in production, InMemorySaver in tests."""

from contextlib import ExitStack

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings

_stack = ExitStack()
_checkpointer: PostgresSaver | None = None


def _to_psycopg_url(url: str) -> str:
    """PostgresSaver expects a psycopg URL, not the SQLAlchemy ``+psycopg`` form."""
    return url.replace("postgresql+psycopg://", "postgresql://")


def get_checkpointer() -> PostgresSaver:
    """Return a shared, durable Postgres checkpointer, running ``setup()`` once."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = _stack.enter_context(
            PostgresSaver.from_conn_string(_to_psycopg_url(settings.database_url))
        )
        _checkpointer.setup()
    return _checkpointer
