"""Phase 15B — vector store backends (pgvector + in-memory fallback).

Covers vector insert, similarity search, metadata filtering, ingestion, and
health reporting against the in-memory store (identical cosine semantics to
pgvector), plus the SQL-construction helpers of the pgvector store that can be
unit-tested without a live Postgres. The pgvector path itself is validated
end-to-end against Supabase separately (see the Phase 15B verification report).
"""

import numpy as np
import pytest

from backend.core.config import Settings
from backend.rag.schema import ALL_COLLECTIONS, FEEDBACK_RECORDS, HISTORICAL_TICKETS
from backend.rag.service import RagService, select_store
from backend.rag.store import (
    InMemoryVectorStore,
    PgVectorStore,
    _vector_literal,
    point_id,
)

DIM = 8  # tiny dims are fine for the in-memory store


def _unit(*nonzero_indices):
    """A simple one-hot-ish vector for deterministic cosine tests."""
    v = np.zeros(DIM, dtype="float32")
    for i in nonzero_indices:
        v[i] = 1.0
    return v


# ---------------------------------------------------------------- in-memory store


@pytest.fixture
def store():
    s = InMemoryVectorStore(Settings(rag_embedding_dim=DIM, vector_store_mode="memory"))
    s.upsert(
        HISTORICAL_TICKETS,
        [
            {"id": "a", "vector": _unit(0, 1), "payload": {"ticket_id": "a", "text": "alpha", "department": "Tech"}},
            {"id": "b", "vector": _unit(0), "payload": {"ticket_id": "b", "text": "beta", "department": "Tech"}},
            {"id": "c", "vector": _unit(5, 6), "payload": {"ticket_id": "c", "text": "gamma", "department": "Billing"}},
        ],
    )
    return s


def test_vector_insert_counts(store):
    assert store.count(HISTORICAL_TICKETS) == 3
    assert store.count(FEEDBACK_RECORDS) == 0


def test_similarity_search_ranks_closest_first(store):
    # Query aligned with 'a' (indices 0,1): 'a' is most similar, then 'b' (0), then 'c'.
    rows = store.search(HISTORICAL_TICKETS, _unit(0, 1), top_k=3)
    ids = [r["payload"]["ticket_id"] for r in rows]
    assert ids[0] == "a"
    assert "c" not in ids[:1]
    assert rows[0]["score"] >= rows[-1]["score"]


def test_score_floor_filters(store):
    # 'c' is orthogonal to the query → score 0, filtered by a positive floor.
    rows = store.search(HISTORICAL_TICKETS, _unit(0, 1), top_k=5, score_floor=0.5)
    assert all(r["payload"]["ticket_id"] != "c" for r in rows)


def test_metadata_filter(store):
    rows = store.search(
        HISTORICAL_TICKETS, _unit(5, 6), top_k=5, filters={"department": "Billing"}
    )
    assert rows and all(r["payload"]["department"] == "Billing" for r in rows)


def test_upsert_is_idempotent(store):
    store.upsert(
        HISTORICAL_TICKETS,
        [{"id": "a", "vector": _unit(2), "payload": {"ticket_id": "a", "text": "alpha v2"}}],
    )
    assert store.count(HISTORICAL_TICKETS) == 3  # replaced, not added


def test_init_collections_creates_all(store):
    store.init_collections()
    for name in ALL_COLLECTIONS:
        assert store.count(name) == 0 or name == HISTORICAL_TICKETS


# ---------------------------------------------------------------- service + health


def _hash_embed(dim):
    import hashlib

    def fn(texts):
        out = np.zeros((len(texts), dim), dtype="float32")
        for i, t in enumerate(texts):
            for w in str(t).lower().split():
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
        return out

    return fn


def test_service_ingest_and_health_reports_memory_mode():
    from backend.rag.embeddings import RagEmbedder

    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    svc = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=_hash_embed(DIM)),
        store=InMemoryVectorStore(settings),
    )
    svc.ingest([{"ticket_id": "x1", "text": "vpn authentication failed", "department": "IT"}])
    health = svc.health()
    assert health["vector_store_mode"] == "memory"
    assert health["collections"][HISTORICAL_TICKETS] == 1
    assert health["embedding_dim"] == DIM


def test_ingest_skips_blank_text():
    from backend.rag.embeddings import RagEmbedder

    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    svc = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=_hash_embed(DIM)),
        store=InMemoryVectorStore(settings),
    )
    assert svc.ingest([{"ticket_id": "blank", "text": "   "}]) == 0


# ---------------------------------------------------------------- store selection


def test_select_store_memory_for_sqlite():
    s = Settings(database_url="sqlite:///x.db", vector_store_mode="auto")
    assert select_store(s).mode == "memory"


def test_select_store_pgvector_for_postgres():
    s = Settings(
        database_url="postgresql://u:p@h:5432/db", vector_store_mode="auto"
    )
    assert select_store(s).mode == "pgvector"


def test_select_store_explicit_override():
    s = Settings(database_url="sqlite:///x.db", vector_store_mode="pgvector")
    assert select_store(s).mode == "pgvector"
    s2 = Settings(database_url="postgresql://u:p@h/db", vector_store_mode="memory")
    assert select_store(s2).mode == "memory"


# ---------------------------------------------------------------- pgvector helpers


def test_vector_literal_format():
    assert _vector_literal([0.0, 1.5, -2.0]) == "[0.0,1.5,-2.0]"


def test_pgvector_table_whitelist_rejects_unknown():
    # Construct against a sqlite URL — no connection is opened by __init__.
    store = PgVectorStore(Settings(database_url="sqlite:///x.db", rag_embedding_dim=DIM))
    assert store.mode == "pgvector"
    assert store._table(HISTORICAL_TICKETS) == "historical_tickets"
    with pytest.raises(ValueError):
        store._table("drop_tables; --")


def test_point_id_is_deterministic():
    assert point_id("abc") == point_id("abc")
    assert point_id("abc") != point_id("xyz")
