"""SQLAlchemy engine and session lifecycle helpers."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all persistence models."""


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a production PostgreSQL or test-friendly SQLite engine."""

    engine_options: dict[str, object] = {"echo": echo}
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            # A shared connection keeps an in-memory database visible across
            # FastAPI requests that execute in different worker threads.
            engine_options["poolclass"] = StaticPool
    else:
        engine_options["pool_pre_ping"] = True
        engine_options["pool_size"] = settings.database_pool_size
        engine_options["max_overflow"] = settings.database_max_overflow
        engine_options["pool_timeout"] = settings.database_pool_timeout_seconds

    database_engine = create_engine(database_url, **engine_options)
    if database_url.startswith("sqlite"):

        @event.listens_for(database_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return database_engine


engine = create_database_engine(settings.database_url, echo=settings.database_echo)
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that closes the session after each request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def transactional_session() -> Iterator[Session]:
    """Provide an atomic session for scripts and service entry points."""

    db = SessionLocal()
    try:
        with db.begin():
            yield db
    finally:
        db.close()
