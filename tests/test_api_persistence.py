"""End-to-end persistence API tests: analyze -> recent / review-queue / review
/ feedback / analytics (Phase 6). Uses in-memory SQLite + a fake pipeline."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.config import SETTINGS  # noqa: E402


class _Engine:
    index_size = 44160
    duplicate_threshold = 0.7623


class _Artifacts:
    tag_list = list(range(28))
    dept_prototypes = {f"D{i}": object() for i in range(10)}


class RoutingFakePipeline:
    """Routes by text: text containing 'review' -> HUMAN_REVIEW, else AUTO_ROUTE."""

    def __init__(self):
        self.artifacts = _Artifacts()
        self.duplicate_engine = _Engine()
        self.routing_sbert = object()

    def process_ticket(self, text, register=True, translate=True):
        review = "review" in text.lower()
        route = "HUMAN_REVIEW" if review else "AUTO_ROUTE"
        return {
            "ticket_id": f"t{abs(hash(text)) % 100000000:08d}",
            "status": "NOT DUPLICATE",
            "route": route,
            "department": "Technical_Support",
            "priority": "critical" if review else "high",
            "priority_confidence": float("nan") if review else 0.82,
            "confidence": 0.74 if review else 0.96,
            "review": review,
            "tags": "network_issue (0.93)",
            "message": "ok",
            "latency": 12.3,
            "is_duplicate": False,
            "duplicate_score": 0.21,
            "duplicate_text": None,
            "duplicate_matched_id": None,
            "explanation": "Ticket processed.",
            "explanation_struct": {
                "routing": {"plain": "p", "evidence": {"gate_rule": "margin_pass"}, "forensics": {}},
                "duplicate": None,
                "priority": {"plain": "p", "evidence": {}, "forensics": {}},
            },
            "original_text": text,
            "routing_text": text,
            "detected_language": "en",
            "translated_text": text,
            "translation_applied": False,
            "routing": {
                "recommended_department": "Technical_Support",
                "margin": 0.2,
                "entropy": 1.6,
                "top_tag_votes": [
                    {"tag": "network_issue", "score": 0.93, "department": "Technical_Support"}
                ],
            },
        }


@pytest.fixture
def client(db_factory):
    app = create_app(pipeline=RoutingFakePipeline(), session_factory=db_factory)
    return TestClient(app)


def test_analyze_persists_and_lists_recent(client):
    r = client.post("/analyze-ticket", json={"text": "server is down"})
    assert r.status_code == 200
    ticket_id = r.json()["ticket_id"]

    recent = client.get("/tickets/recent").json()
    assert any(t["ticket_id"] == ticket_id for t in recent)

    detail = client.get(f"/tickets/{ticket_id}").json()
    assert detail["ticket_id"] == ticket_id
    assert detail["route"] == "AUTO_ROUTE"


def test_ticket_detail_404(client):
    assert client.get("/tickets/doesnotexist").status_code == 404


def test_review_queue_flow(client):
    # A review-routed ticket lands in the queue.
    r = client.post("/analyze-ticket", json={"text": "please review this escalation"})
    ticket_id = r.json()["ticket_id"]

    queue = client.get("/review-queue").json()
    assert any(item["ticket_id"] == ticket_id for item in queue)

    # Submit an override.
    review = client.post(
        f"/tickets/{ticket_id}/review",
        json={"action": "overridden", "final_department": "IT_Support"},
    )
    assert review.status_code == 200
    assert review.json()["final_department"] == "IT_Support"

    # Queue is now empty; feedback recorded.
    assert client.get("/review-queue").json() == []
    feedback = client.get("/feedback").json()
    assert any(
        f["ticket_id"] == ticket_id and f["final_department"] == "IT_Support"
        for f in feedback
    )


def test_review_bad_action_400(client):
    r = client.post("/analyze-ticket", json={"text": "needs review now"})
    ticket_id = r.json()["ticket_id"]
    bad = client.post(f"/tickets/{ticket_id}/review", json={"action": "nonsense"})
    assert bad.status_code == 400


def test_review_missing_ticket_404(client):
    r = client.post("/tickets/ghost/review", json={"action": "approved"})
    assert r.status_code == 404


def test_analytics_summary(client):
    client.post("/analyze-ticket", json={"text": "server down one"})
    client.post("/analyze-ticket", json={"text": "please review two"})
    summary = client.get("/analytics/summary").json()
    assert summary["total_tickets"] == 2
    assert summary["route_mode_counts"]["AUTO_ROUTE"] == 1
    assert summary["route_mode_counts"]["HUMAN_REVIEW"] == 1
    assert summary["language_counts"]["en"] == 2


def test_analytics_monitoring(client):
    # Two auto-routed (conf 0.96) and one review-routed (conf 0.74) ticket.
    client.post("/analyze-ticket", json={"text": "server down one"})
    client.post("/analyze-ticket", json={"text": "disk full two"})
    r = client.post("/analyze-ticket", json={"text": "please review three"})
    review_id = r.json()["ticket_id"]
    client.post(
        f"/tickets/{review_id}/review",
        json={"action": "overridden", "final_department": "IT_Support"},
    )

    mon = client.get("/analytics/monitoring").json()
    assert mon["total_tickets"] == 3

    hist = mon["confidence_histogram"]
    assert len(hist["bins"]) == 10
    # The fake pipeline emits gate_rule="margin_pass" for every ticket.
    assert hist["thresholds"]["hybrid_floor"] == SETTINGS.hybrid_floor
    assert mon["gate_rule_counts"]["margin_pass"] == 3
    # Auto tickets at 0.96 -> top bin; review ticket at 0.74 -> bin 7.
    assert hist["series"]["AUTO_ROUTE"][9] == 2
    assert hist["series"]["HUMAN_REVIEW"][7] == 1

    # The override produced a predicted->final flow link and one reroute.
    flow = {(f["predicted"], f["final"]): f["count"] for f in mon["predicted_vs_final"]}
    assert flow[("Technical_Support", "IT_Support")] == 1
    assert mon["routing_accuracy"]["total_reviewed"] == 1
    assert mon["routing_accuracy"]["changes"] == 1
