"""SQLAlchemy 2.0 engine + session factory (Phase 6).

SQLite by default (file at `main/itars.db`), Postgres-ready via `ITARS_DATABASE_URL`.
In-memory SQLite (`sqlite://` / `:memory:`) uses StaticPool so a single shared
connection backs the whole app — required for tests and for the threaded API.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str, *, echo: bool = False) -> Engine:
    connect_args: dict = {}
    kwargs: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url or url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(url, echo=echo, future=True, connect_args=connect_args, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )


def init_db(engine: Engine) -> None:
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
