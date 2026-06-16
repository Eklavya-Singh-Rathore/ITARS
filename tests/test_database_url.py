"""Phase 15A — Database URL normalization + Supabase pooler detection.

Guards the engine-building logic so connection-string handling stays correct
when teams paste any of the URL variants Supabase/self-hosted Postgres can
hand out.
"""

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy.pool import NullPool, StaticPool  # noqa: E402

from backend.repositories.database import (  # noqa: E402
    _is_supabase_txn_pooler,
    make_engine,
    normalize_database_url,
)


def test_normalize_bare_postgresql_adds_psycopg_driver():
    assert normalize_database_url("postgresql://u:p@h:5432/db") == (
        "postgresql+psycopg://u:p@h:5432/db"
    )


def test_normalize_legacy_postgres_scheme():
    assert normalize_database_url("postgres://u:p@h:5432/db") == (
        "postgresql+psycopg://u:p@h:5432/db"
    )


def test_normalize_already_explicit_is_unchanged():
    url = "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_database_url(url) == url


def test_normalize_sqlite_is_unchanged():
    url = "sqlite:///itars.db"
    assert normalize_database_url(url) == url


def test_supabase_pooler_detection_for_transaction_mode():
    assert _is_supabase_txn_pooler(
        "postgresql+psycopg://postgres.abc:secret@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"
    )


def test_supabase_pooler_detection_rejects_session_mode_port():
    # Session mode lives on 5432 — must NOT be treated as the tx pooler.
    assert not _is_supabase_txn_pooler(
        "postgresql+psycopg://postgres.abc:secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    )


def test_supabase_pooler_detection_rejects_direct_connection():
    # Direct connection: 5432 on db.<ref>.supabase.co — not the pooler host.
    assert not _is_supabase_txn_pooler(
        "postgresql+psycopg://postgres:secret@db.abc.supabase.co:5432/postgres"
    )


def test_make_engine_sqlite_in_memory_uses_static_pool():
    engine = make_engine("sqlite://")
    assert engine.pool.__class__ is StaticPool


def test_make_engine_pg_url_is_normalized():
    # Use a URL with reserved port (1) that no driver will reach during engine
    # construction; SQLAlchemy parses lazily so this is safe.
    engine = make_engine("postgresql://u:p@h:1/db")
    assert str(engine.url).startswith("postgresql+psycopg://")


def test_make_engine_supabase_tx_pooler_uses_null_pool():
    engine = make_engine(
        "postgresql://postgres.abc:secret@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"
    )
    assert engine.pool.__class__ is NullPool


def test_make_engine_supabase_session_pooler_uses_default_pool():
    # Session mode should use the standard QueuePool (not NullPool).
    engine = make_engine(
        "postgresql://postgres.abc:secret@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
    )
    assert engine.pool.__class__ is not NullPool
