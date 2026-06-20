"""RAG API tests — real RagService (in-memory vector store + fake embedder)."""

import hashlib

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.config import Settings  # noqa: E402
from backend.rag.embeddings import RagEmbedder  # noqa: E402
from backend.rag.service import RagService  # noqa: E402
from backend.rag.store import InMemoryVectorStore  # noqa: E402
from backend.repositories import tickets as repo  # noqa: E402

DIM = 384
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
            out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    return out


def _db_result(ticket_id: str, text: str) -> dict:
    return {
        "ticket_id": ticket_id,
        "route": "HUMAN_REVIEW",
        "department": "Technical_Support",
        "priority": "critical",
        "priority_confidence": 0.8,
        "confidence": 0.74,
        "review": True,
        "tags": "incident (1.00)",
        "latency": 12.0,
        "is_duplicate": False,
        "duplicate_score": 0.2,
        "duplicate_text": None,
        "duplicate_matched_id": None,
        "duplicate_threshold": 0.76,
        "explanation": "x",
        "explanation_struct": {"routing": {}, "duplicate": None, "priority": {}},
        "original_text": text,
        "routing_text": text,
        "detected_language": "en",
        "translation_applied": False,
        "routing": {"recommended_department": "Technical_Support", "margin": 0.1, "entropy": 1.6, "top_tag_votes": []},
    }


@pytest.fixture
def client(db_factory):
    with db_factory() as session:
        repo.save_analysis(
            session, _db_result("prod0001", "production server down unreachable outage")
        )
    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    rag = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=fake_embed),
        store=InMemoryVectorStore(settings),
    )
    rag.ingest(
        [
            {"ticket_id": "h1", "text": "production server down unreachable outage incident", "department": "Technical_Support", "priority": "high"},
            {"ticket_id": "h2", "text": "billing charged twice subscription refund", "department": "Billing_And_Payments", "priority": "medium"},
        ]
    )
    app = create_app(pipeline=object(), session_factory=db_factory, rag=rag)
    return TestClient(app)


def test_rag_health(client):
    body = client.get("/rag/health").json()
    assert body["collections"]["historical_tickets"] == 2
    assert body["embedding_dim"] == DIM


def test_rag_search_returns_cited_results(client):
    r = client.post("/rag/search", json={"query": "production server down"})
    assert r.status_code == 200
    results = r.json()
    assert results
    assert results[0]["ticket_id"] == "h1"
    assert results[0]["text"]  # citation text present
    assert results[0]["score"] >= results[-1]["score"]


def test_rag_search_department_filter(client):
    r = client.post(
        "/rag/search",
        json={
            "query": "charged subscription refund",
            "department": "Billing_And_Payments",
            "top_k": 5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body and all(x["department"] == "Billing_And_Payments" for x in body)


def test_similar_tickets_endpoint(client):
    r = client.get("/tickets/prod0001/similar")
    assert r.status_code == 200
    results = r.json()
    assert any(x["ticket_id"] == "h1" for x in results)
    assert all(x["ticket_id"] != "prod0001" for x in results)


def test_similar_tickets_404(client):
    assert client.get("/tickets/ghost/similar").status_code == 404


def test_review_override_feeds_rag_feedback_records(client):
    # The feedback loop (Phase 11): an override ingests the human-verified
    # routing into the RAG feedback_records collection.
    before = client.get("/rag/health").json()["collections"].get("feedback_records", 0)
    r = client.post(
        "/tickets/prod0001/review",
        json={
            "action": "overridden",
            "final_department": "IT_Support",
            "correction_reason": "wrong_department",
        },
    )
    assert r.status_code == 200
    after = client.get("/rag/health").json()["collections"]["feedback_records"]
    assert after == before + 1


def test_get_rag_dependency_raises_503_when_absent():
    import types

    from fastapi import HTTPException

    from backend.api.deps import get_rag

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace())
    )
    with pytest.raises(HTTPException) as excinfo:
        get_rag(request)
    assert excinfo.value.status_code == 503
