"""SQLAlchemy 2.0 engine + session factory.

SQLite by default (file at `main/itars.db`), Postgres-ready via
`ITARS_DATABASE_URL`. In-memory SQLite uses `StaticPool` so a single shared
connection backs the whole app — required for tests and for the threaded API.

Phase 15A adds first-class Postgres support (Supabase / self-host). The engine
accepts `postgresql://`, `postgresql+psycopg://`, and `postgres://` (legacy
alias) interchangeably — the URL is normalized to the psycopg-v3 driver. When
the URL targets Supabase's *transaction-mode* pooler (port 6543), `NullPool` is
selected automatically per the Supabase + SQLAlchemy guide, since that mode
doesn't allow prepared statements or long-lived connections.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Coerce Postgres URL variants to the explicit psycopg-v3 driver scheme.

    Supabase and many Postgres providers hand out `postgres://...` or
    `postgresql://...` strings. SQLAlchemy 2.0 requires the explicit driver
    (`postgresql+psycopg://...`) — we add it transparently so callers don't
    have to edit the connection string when they switch providers.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _is_supabase_txn_pooler(url: str) -> bool:
    """True for the Supabase transaction-mode pooler (port 6543).

    That mode doesn't keep server-side state between transactions, so the
    Supabase + SQLAlchemy guide says to disable SQLAlchemy's pool with
    `NullPool` and let the server-side pooler do the multiplexing.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.port == 6543 and (parts.hostname or "").endswith(".pooler.supabase.com")


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """Build the SQLAlchemy engine for the configured database URL.

    Dialect handling:
      * sqlite — disable `check_same_thread`; use StaticPool for in-memory dbs.
      * postgresql — accept either the explicit `+psycopg` driver or the bare
        scheme (we normalize it); attach NullPool when the URL points at the
        Supabase transaction-mode pooler.
    """
    url = normalize_database_url(url)
    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url or url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    elif url.startswith("postgresql"):
        if _is_supabase_txn_pooler(url):
            # Server-side pooler in tx mode handles multiplexing; the
            # SQLAlchemy-side pool must not hold connections across requests.
            kwargs["poolclass"] = NullPool
            # Prepared statements aren't supported on the tx pooler — psycopg's
            # auto-prepare must be off, and SQLAlchemy must not cache plans.
            connect_args["prepare_threshold"] = None

    return create_engine(url, echo=echo, future=True, connect_args=connect_args, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True
    )


def init_db(engine: Engine) -> None:
    """Create the schema if it doesn't already exist.

    Idempotent: `create_all` skips tables that already exist. Safe to call on
    every app boot, both for fresh SQLite files and for a Supabase Postgres
    that was provisioned out-of-band via the dashboard / a tracked migration.
    """
    from . import models  # noqa: F401  registers tables on Base.metadata

    Base.metadata.create_all(engine)
