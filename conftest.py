"""Pytest bootstrap: make `backend` importable from the main/ root."""

import sys
from pathlib import Path

import pytest

MAIN_DIR = Path(__file__).resolve().parent
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))


@pytest.fixture
def db_factory():
    """A fresh in-memory SQLite session factory per test (no files written)."""
    from backend.repositories.database import (
        init_db,
        make_engine,
        make_session_factory,
    )

    engine = make_engine("sqlite://")
    init_db(engine)
    return make_session_factory(engine)

