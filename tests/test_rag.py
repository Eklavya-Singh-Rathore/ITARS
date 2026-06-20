"""RAG retrieval tests — in-memory vector store + deterministic fake embedder.

No model download / no Postgres needed: a word-hash embedder gives
overlap-driven cosine similarity, which is enough to exercise ingest, ranking,
the score floor, filters, citations, and self-exclusion. Production uses
pgvector (Supabase) with identical cosine semantics.
"""

import hashlib

import numpy as np
import pytest

from backend.core.config import Settings  # noqa: E402
from backend.rag.embeddings import RagEmbedder  # noqa: E402
from backend.rag.schema import HISTORICAL_TICKETS  # noqa: E402
from backend.rag.service import RagService  # noqa: E402
from backend.rag.store import InMemoryVectorStore  # noqa: E402

DIM = 384  # match the real BGE-small dim; avoids word-hash collisions

# Ignore the BGE query prefix + common stopwords so only content words drive
# similarity (the real BGE model handles this; the fake needs help).
STOP = set(
    "represent this sentence for searching relevant passages the a an is are was "
    "were and or to of my that i it in on again please".split()
)


def fake_embed(texts):
    out = np.zeros((len(texts), DIM), dtype="float32")
    for i, text in enumerate(texts):
        for word in str(text).lower().split():
            if word in STOP:
                continue
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM
            out[i, idx] += 1.0
    return out


TICKETS = [
    {"ticket_id": "t1", "text": "production server is down and unreachable", "department": "Technical_Support", "priority": "critical"},
    {"ticket_id": "t2", "text": "the production servers are down again this morning", "department": "Technical_Support", "priority": "high"},
    {"ticket_id": "t3", "text": "i was charged twice for my subscription refund please", "department": "Billing_And_Payments", "priority": "medium"},
    {"ticket_id": "t4", "text": "cannot access the vpn authentication failed", "department": "IT_Support", "priority": "high"},
]


@pytest.fixture
def rag():
    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    service = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=fake_embed),
        store=InMemoryVectorStore(settings),
    )
    service.ingest(TICKETS)
    return service


def test_ingest_counts(rag):
    health = rag.health()
    assert health["collections"][HISTORICAL_TICKETS] == 4


def test_search_ranks_relevant_first(rag):
    results = rag.search("production servers down", score_floor=0.1)
    assert results, "expected at least one match"
    # The two production-server tickets should outrank billing/vpn.
    top_ids = [r["ticket_id"] for r in results[:2]]
    assert set(top_ids) == {"t1", "t2"}
    # Citations + scores present.
    assert results[0]["text"]
    assert results[0]["score"] >= results[-1]["score"]


def test_score_floor_suppresses_weak_matches(rag):
    # Nothing should clear a near-perfect floor for an unrelated query.
    results = rag.search("production servers down", score_floor=0.999)
    assert results == []


def test_department_filter(rag):
    results = rag.search(
        "down", filters={"department": "Billing_And_Payments"}, score_floor=0.0
    )
    assert all(r["department"] == "Billing_And_Payments" for r in results)


def test_similar_excludes_self(rag):
    results = rag.similar_tickets(
        "production server is down and unreachable",
        exclude_ticket_id="t1",
        score_floor=0.1,
    )
    assert all(r["ticket_id"] != "t1" for r in results)
    assert any(r["ticket_id"] == "t2" for r in results)


def test_empty_query_corpus_returns_empty():
    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    service = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=fake_embed),
        store=InMemoryVectorStore(settings),
    )
    assert service.search("anything", score_floor=0.0) == []
    assert service.health()["collections"][HISTORICAL_TICKETS] == 0


def test_ingest_skips_blank_text(rag):
    added = rag.ingest([{"ticket_id": "blank", "text": "   "}])
    assert added == 0
