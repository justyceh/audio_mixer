"""Shared FastAPI dependencies."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from api.db.session import SessionLocal, get_engine


def get_db() -> Iterator[Session]:
    get_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user() -> None:
    """Authentication hook.

    The MVP is single-user and unauthenticated, so this returns None. When auth is
    added, resolve the user here and use it in services to scope queries by owner;
    routes already depend on this, so their signatures won't need to change.
    """
    return None
