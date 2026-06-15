"""End-to-end smoke test for the ported pipeline.

Requires an environment with the heavy ML stack (pandas, faiss, sentence-transformers,
torch) AND first-run network access to pull the public SBERT encoders. Skips cleanly
when those are unavailable so the lightweight feature-parity test can always run.
"""

import pytest

pytest.importorskip("pandas")
pytest.importorskip("faiss")
pytest.importorskip("sentence_transformers")


EXAMPLES = [
    "My laptop screen is flickering and sometimes goes completely black.",
    "I cannot access the company VPN from my home network. Authentication failed.",
    "We need to upgrade our database server; it is running out of storage.",
    "I was charged twice for my last month's subscription. Please refund.",
    "The email server has been down since this morning. This is critical!",
    "Can you provide training materials for the new CRM software?",
]

REQUIRED_KEYS = {
    "ticket_id",
    "status",
    "route",
    "department",
    "priority",
    "confidence",
    "review",
    "tags",
    "explanation",
    "routing",
    "log_row",
}

VALID_ROUTES = {"AUTO_ROUTE", "AUTO_ROUTE_FLAGGED", "HUMAN_REVIEW"}


@pytest.fixture(scope="module")
def pipeline():
    try:
        from backend.services.pipeline import RoutingPipeline

        return RoutingPipeline()
    except Exception as exc:  # missing artifacts / no network for encoders
        pytest.skip(f"pipeline unavailable in this environment: {exc}")


def test_examples_route_with_full_structure(pipeline):
    for text in EXAMPLES:
        result = pipeline.process_ticket(text, register=False)
        assert REQUIRED_KEYS.issubset(result.keys())
        assert result["route"] in VALID_ROUTES
        assert result["department"]
        assert result["priority"].lower() in {"low", "medium", "high", "critical"}
        # priority confidence is always computed (no empty column like the old CSV)
        assert "priority_confidence" in result


def test_duplicate_detected_on_resubmit(pipeline):
    text = "production servers are down, please fix asap"
    first = pipeline.process_ticket(text, register=True)
    assert first["status"] in {"DUPLICATE", "NOT DUPLICATE"}
    second = pipeline.process_ticket(text, register=False)
    # An identical resubmission should be caught as a duplicate.
    assert second["is_duplicate"] is True
    assert second["duplicate_score"] >= float(pipeline.duplicate_engine.duplicate_threshold)
