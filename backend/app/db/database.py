"""Engine and session lifecycle.

The engine is module-level but *rebindable*. That matters for two reasons:

* tests point each test at its own database file, and
* the restart-persistence test must be able to throw the entire engine away and
  rebuild it from nothing, proving data lives in the database rather than in a
  Python object that happened to stay alive.

Nothing outside this module may hold a long-lived ``Session``. Sessions are
per-request (or per-unit-of-work) and are closed by whoever opened them.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import database_url


class Base(DeclarativeBase):
    """Declarative base for every persisted model."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless asked not to.

    Case isolation is expressed partly through composite foreign keys, so an
    unenforced constraint would make the schema weaker in development than in
    PostgreSQL, which is exactly where a cross-case leak would hide.
    """
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _build_engine(url: str) -> Engine:
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # FastAPI serves sync endpoints from a threadpool; the connection may
        # legitimately be used from a different thread than it was created on.
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, connect_args=connect_args)


def configure(url: str | None = None) -> Engine:
    """(Re)bind the engine, disposing any previous one."""
    global _engine, _session_factory
    dispose()
    _engine = _build_engine(url or database_url())
    _session_factory = sessionmaker(
        bind=_engine, autoflush=False, expire_on_commit=False, future=True
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure()
    assert _session_factory is not None
    return _session_factory


def dispose() -> None:
    """Drop the engine and its pool entirely."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def create_all() -> None:
    """Create any missing tables. Import of models registers them on the metadata."""
    from app.db import models  # noqa: F401  (registers mappings)

    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.drop_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """A unit of work that commits on success and rolls back on failure."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency.

    The session is *not* committed here. Write paths commit explicitly once the
    whole unit of work has succeeded, so a request that fails part-way leaves no
    partially-projected case behind.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
