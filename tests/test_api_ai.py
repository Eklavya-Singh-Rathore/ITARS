"""AI assistance API tests (Phase 9) — Echo gateway + in-memory RAG + SQLite."""

import hashlib

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.config import Settings  # noqa: E402
from backend.core.llm.gateway import LLMGateway  # noqa: E402
from backend.core.llm.providers import EchoProvider  # noqa: E402
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
        "ticket_id": ticket_id, "route": "HUMAN_REVIEW", "department": "Technical_Support",
        "priority": "critical", "priority_confidence": 0.8, "confidence": 0.74, "review": True,
        "tags": "incident (1.00)", "latency": 12.0, "is_duplicate": False, "duplicate_score": 0.2,
        "duplicate_text": None, "duplicate_matched_id": None, "duplicate_threshold": 0.76,
        "explanation": "x", "explanation_struct": {"routing": {}, "duplicate": None, "priority": {}},
        "original_text": text, "routing_text": text, "detected_language": "en",
        "translation_applied": False,
        "routing": {"recommended_department": "Technical_Support", "margin": 0.1, "entropy": 1.6, "top_tag_votes": []},
    }


@pytest.fixture
def client(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _db_result("prod0001", "production server down outage"))
        repo.save_analysis(session, _db_result("bill0001", "billing question about my invoice"))
    settings = Settings(rag_embedding_dim=DIM, vector_store_mode="memory")
    rag = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=fake_embed),
        store=InMemoryVectorStore(settings),
    )
    rag.ingest([{"ticket_id": "h1", "text": "production server down outage incident", "department": "Technical_Support"}])
    gateway = LLMGateway(settings, providers={"echo": EchoProvider()}, primary="echo", fallback=[])
    app = create_app(pipeline=object(), session_factory=db_factory, rag=rag, llm=gateway)
    return TestClient(app)


def test_ai_summary(client):
    r = client.post("/ai/summary", json={"text": "production server down outage"})
    assert r.status_code == 200
    body = r.json()
    assert body["ai_assisted"] is True
    assert body["advisory"] is True
    assert any(c["ticket_id"] == "h1" for c in body["citations"])


def test_ai_explanation(client):
    r = client.post(
        "/ai/explanation",
        json={"department": "IT_Support", "route": "AUTO_ROUTE", "explanation": {"plain": "x"}},
    )
    assert r.status_code == 200
    assert r.json()["ai_assisted"] is True


def test_ai_recommendation_ok_with_citations(client):
    r = client.post("/ai/recommendation", json={"ticket_id": "prod0001"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["advisory"] is True
    assert body["recommendation"]
    assert any(c["ticket_id"] == "h1" for c in body["citations"])


def test_ai_recommendation_insufficient_evidence(client):
    # The billing ticket has no similar production-incident match -> insufficient.
    r = client.post("/ai/recommendation", json={"ticket_id": "bill0001"})
    assert r.status_code == 200
    assert r.json()["status"] == "insufficient_evidence"


def test_ai_recommendation_404(client):
    assert client.post("/ai/recommendation", json={"ticket_id": "ghost"}).status_code == 404


def test_ai_recommendation_requires_input(client):
    assert client.post("/ai/recommendation", json={}).status_code == 400


def test_ai_actions(client):
    r = client.post("/ai/actions", json={"ticket_id": "prod0001"})
    assert r.status_code == 200
    body = r.json()
    assert body["ai_assisted"] is True
    assert body["text"]


def test_ai_health(client):
    body = client.get("/ai/health").json()
    assert body["rag_available"] is True
    assert "llm" in body
    assert "retrieval_floor" in body
