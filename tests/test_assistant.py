"""AssistantService tests (Phase 9) — offline via Echo + in-memory RAG."""

import hashlib

import numpy as np
import pytest

from backend.core.config import Settings
from backend.core.llm.base import LLMError, LLMProvider, LLMRequest, LLMResponse
from backend.core.llm.gateway import LLMGateway
from backend.core.llm.providers import EchoProvider
from backend.services.assistant import AssistantService

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


def _echo_gateway():
    return LLMGateway(Settings(), providers={"echo": EchoProvider()}, primary="echo", fallback=[])


def _rag_with(records):
    pytest.importorskip("qdrant_client")
    from backend.rag.embeddings import RagEmbedder
    from backend.rag.service import RagService
    from backend.rag.store import QdrantStore

    settings = Settings(rag_embedding_dim=DIM, qdrant_url=":memory:")
    service = RagService(
        settings,
        embedder=RagEmbedder(settings, embed_fn=fake_embed),
        store=QdrantStore(settings),
    )
    if records:
        service.ingest(records)
    return service


class FailingProvider(LLMProvider):
    name = "failing"
    model = "x"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMError("down")


# ------------------------------------------------------------------- summary
def test_summary_grounded_with_citations():
    rag = _rag_with(
        [{"ticket_id": "h1", "text": "production server down outage incident", "department": "Technical_Support"}]
    )
    assistant = AssistantService(llm=_echo_gateway(), rag=rag)
    out = assistant.summary("production server down outage")
    assert out["ai_assisted"] is True
    assert out["advisory"] is True
    assert any(c["ticket_id"] == "h1" for c in out["citations"])
    assert out["provider"] == "echo"


def test_summary_works_without_rag():
    assistant = AssistantService(llm=_echo_gateway(), rag=None)
    out = assistant.summary("vpn authentication failing")
    assert out["ai_assisted"] is True
    assert out["citations"] == []


def test_summary_degrades_when_llm_fails():
    gw = LLMGateway(Settings(), providers={"failing": FailingProvider()}, primary="failing", fallback=[])
    assistant = AssistantService(llm=gw, rag=None)
    out = assistant.summary("anything")
    assert out["ai_assisted"] is False
    assert "unavailable" in out["text"].lower()


# --------------------------------------------------------------- explanation
def test_explanation_generated_from_dict():
    assistant = AssistantService(llm=_echo_gateway(), rag=None)
    out = assistant.explanation(
        department="IT_Support",
        route="AUTO_ROUTE",
        explanation={"plain": "routed to IT", "evidence": {"gate_rule": "margin_pass"}},
    )
    assert out["ai_assisted"] is True
    assert out["citations"] == []


# ------------------------------------------------------------- recommendation
def test_recommendation_insufficient_evidence_when_no_retrieval():
    assistant = AssistantService(llm=_echo_gateway(), rag=None)  # no rag -> no grounding
    out = assistant.recommendation(ticket_text="x", routing={})
    assert out["status"] == "insufficient_evidence"
    assert out["recommendation"] is None
    assert out["ai_assisted"] is False


def test_recommendation_insufficient_when_below_floor():
    # Corpus has an unrelated ticket; query won't clear the 0.5 floor.
    rag = _rag_with([{"ticket_id": "h9", "text": "billing refund subscription charged", "department": "Billing_And_Payments"}])
    assistant = AssistantService(llm=_echo_gateway(), rag=rag)
    out = assistant.recommendation(ticket_text="kernel panic on the database server", routing={})
    assert out["status"] == "insufficient_evidence"


def test_recommendation_ok_with_citations():
    rag = _rag_with([{"ticket_id": "h1", "text": "production server down outage incident", "department": "Technical_Support"}])
    assistant = AssistantService(llm=_echo_gateway(), rag=rag)
    out = assistant.recommendation(
        ticket_text="production server down outage", routing={"department": "Technical_Support"}
    )
    assert out["status"] == "ok"
    assert out["advisory"] is True
    assert out["recommendation"]
    assert any(c["ticket_id"] == "h1" for c in out["citations"])


def test_health_shape():
    assistant = AssistantService(llm=_echo_gateway(), rag=None)
    health = assistant.health()
    assert health["rag_available"] is False
    assert "llm" in health
    assert "retrieval_floor" in health
