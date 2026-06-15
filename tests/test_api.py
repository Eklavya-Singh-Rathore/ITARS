"""API contract tests using an injected fake pipeline (no heavy ML deps)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402


class _Engine:
    index_size = 44160
    duplicate_threshold = 0.7623


class _Artifacts:
    tag_list = list(range(28))
    dept_prototypes = {f"D{i}": object() for i in range(10)}


class FakePipeline:
    """Returns canned results; includes NaN priority_confidence to test sanitizing."""

    def __init__(self):
        self.artifacts = _Artifacts()
        self.duplicate_engine = _Engine()
        self.routing_sbert = object()

    def process_ticket(self, text, register=True, translate=True):
        return {
            "ticket_id": "abc12345",
            "status": "NOT DUPLICATE",
            "route": "AUTO_ROUTE",
            "department": "Technical_Support",
            "priority": "high",
            "priority_confidence": float("nan"),
            "confidence": 0.96,
            "review": False,
            "tags": "network_issue (0.93)",
            "message": "ok",
            "latency": 12.3,
            "is_duplicate": False,
            "duplicate_score": 0.21,
            "duplicate_text": None,
            "explanation": "Ticket processed.",
            "original_text": text,
            "detected_language": "en",
            "translated_text": text,
            "translation_applied": False,
            "routing": {
                "top_tag_votes": [
                    {"tag": "network_issue", "score": 0.93, "department": "Technical_Support"}
                ],
                "margin": 0.2,
                "entropy": 1.6,
                "priority_confidence": float("nan"),
            },
            "explanation_struct": {
                "routing": {
                    "plain": "Auto-routed to Technical Support because network_issue maps there.",
                    "evidence": {
                        "department": "Technical_Support",
                        "tag_votes": [
                            {
                                "tag": "network_issue",
                                "score": 0.93,
                                "department": "Technical_Support",
                            }
                        ],
                        "gate_rule": "margin_pass",
                    },
                    "forensics": {"margin": 0.2, "entropy": 1.6},
                },
                "duplicate": None,
                "priority": {
                    "plain": "Predicted high priority; urgency cues: down.",
                    "evidence": {"priority": "high", "urgency_words": ["down"]},
                    "forensics": {"handcrafted_features": {"urgency_count": 1}},
                },
            },
        }


    def route_only(self, text):
        return {
            "mode": "AUTO_ROUTE",
            "department": "Technical_Support",
            "recommended_department": "Technical_Support",
            "priority": "high",
            "priority_confidence": float("nan"),
            "hybrid_confidence": 0.96,
            "review": False,
            "margin": 0.2,
            "entropy": 1.6,
            "top_tag_votes": [
                {"tag": "network_issue", "score": 0.93, "department": "Technical_Support"}
            ],
            "note": "Stage 2 pass",
        }

    def check_duplicate(self, text):
        return {
            "is_duplicate": True,
            "duplicate_score": 0.88,
            "matched_text": "production servers down",
            "matched_id": "f2bbf3c1",
            "threshold": 0.7623,
        }


class FakeTranslation:
    def translate(self, text, detected_lang=None):
        return {
            "original_text": text,
            "detected_language": "es",
            "translated_text": "the production server is down",
            "translation_applied": True,
            "model": "Helsinki-NLP/opus-mt-ROMANCE-en",
            "error": None,
        }


@pytest.fixture
def client(db_factory):
    return TestClient(
        create_app(
            pipeline=FakePipeline(),
            translation=FakeTranslation(),
            session_factory=db_factory,
        )
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["tags"] == 28
    assert body["departments"] == 10
    assert body["encoders_loaded"] is True


def test_analyze_ticket(client):
    r = client.post("/analyze-ticket", json={"text": "server down", "register": False})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "AUTO_ROUTE"
    assert body["department"] == "Technical_Support"
    assert body["priority_confidence"] is None  # NaN sanitized
    assert body["routing"]["priority_confidence"] is None  # nested NaN sanitized
    assert len(body["tag_votes"]) == 1
    assert body["original_text"] == "server down"
    assert body["translation_applied"] is False
    # Layered explainability surfaces on every ticket.
    assert body["explanation_layers"]["routing"]["evidence"]["gate_rule"] == "margin_pass"
    assert body["explanation_layers"]["duplicate"] is None
    assert "down" in body["explanation_layers"]["priority"]["evidence"]["urgency_words"]


def test_analyze_ticket_empty_text_422(client):
    r = client.post("/analyze-ticket", json={"text": ""})
    assert r.status_code == 422


def test_route(client):
    r = client.post("/route", json={"text": "server down"})
    assert r.status_code == 200
    assert r.json()["mode"] == "AUTO_ROUTE"


def test_duplicate_check(client):
    r = client.post("/duplicate-check", json={"text": "production servers down"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_duplicate"] is True
    assert body["matched_id"] == "f2bbf3c1"


def test_translate(client):
    r = client.post("/translate", json={"text": "el servidor esta caido"})
    assert r.status_code == 200
    body = r.json()
    assert body["detected_language"] == "es"
    assert body["translated_text"] == "the production server is down"
    assert body["original_text"] == "el servidor esta caido"


def test_translate_unsupported_target(client):
    r = client.post("/translate", json={"text": "hola", "target_lang": "fr"})
    assert r.status_code == 400


def test_metrics_increment(client):
    client.post("/analyze-ticket", json={"text": "server down", "register": False})
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["requests_total"] >= 1
    assert body["route_mode_counts"].get("AUTO_ROUTE", 0) >= 1


def test_openapi_renders(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for endpoint in ["/analyze-ticket", "/route", "/duplicate-check", "/translate", "/health", "/metrics"]:
        assert endpoint in paths
