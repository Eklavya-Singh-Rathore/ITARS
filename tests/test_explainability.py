"""ExplainabilityService tests (no heavy deps — uses pure-python routing dicts)."""

from backend.services.explainability import (
    build_ticket_explanation,
    explain_duplicate,
    explain_priority,
    explain_routing,
)
from backend.services.features import extract_handcrafted_with_evidence


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _auto_route_routing() -> dict:
    return {
        "mode": "AUTO_ROUTE",
        "department": "Technical_Support",
        "recommended_department": "Technical_Support",
        "priority": "high",
        "priority_confidence": 0.82,
        "hybrid_confidence": 0.96,
        "review": False,
        "margin": 0.18,
        "entropy": 1.6,
        "best_details": {
            "department": "Technical_Support",
            "classifier_confidence": 0.99,
            "semantic_similarity": 0.88,
            "raw_semantic_similarity": 0.76,
            "hybrid_confidence": 0.96,
        },
        "department_details": {
            "Technical_Support": {
                "department": "Technical_Support",
                "hybrid_confidence": 0.96,
                "classifier_confidence": 0.99,
                "semantic_similarity": 0.88,
            },
            "IT_Support": {
                "department": "IT_Support",
                "hybrid_confidence": 0.72,
                "classifier_confidence": 0.61,
                "semantic_similarity": 0.55,
            },
        },
        "top_tag_votes": [
            {"tag": "network_issue", "score": 0.93, "department": "Technical_Support"},
            {"tag": "performance_issue", "score": 0.51, "department": "Technical_Support"},
        ],
        "review_decision": {
            "base_mode": "AUTO_ROUTE",
            "final_mode": "AUTO_ROUTE",
            "forced_human_review": False,
            "percentile_threshold": 0.30,
            "fallback_threshold": 0.30,
            "reason": "Ticket passed the controlled review check and remains AUTO_ROUTE.",
            "target_review_fraction": 0.15,
            "triggered_rules": [],
        },
        "note": "Stage 2 pass: hybrid_confidence=0.96, margin=0.18, entropy=1.6.",
    }


def _forced_review_routing() -> dict:
    routing = _auto_route_routing()
    routing["mode"] = "HUMAN_REVIEW"
    routing["review"] = True
    routing["review_decision"] = {
        "base_mode": "AUTO_ROUTE",
        "final_mode": "HUMAN_REVIEW",
        "forced_human_review": True,
        "percentile_threshold": 0.30,
        "fallback_threshold": 0.30,
        "target_review_fraction": 0.15,
        "reason": "Controlled review injection forced HUMAN_REVIEW.",
        "triggered_rules": ["percentile"],
    }
    return routing


def test_routing_plain_mentions_dept_and_tags():
    explanation = explain_routing(_auto_route_routing())
    assert "Technical Support" in explanation["plain"]
    assert "network_issue" in explanation["plain"]


def test_routing_evidence_carries_tag_votes_and_gate_rule():
    explanation = explain_routing(_auto_route_routing())
    evidence = explanation["evidence"]
    assert evidence["gate_rule"] == "margin_pass"
    assert len(evidence["tag_votes"]) == 2
    assert evidence["tag_votes"][0]["tag"] == "network_issue"
    assert evidence["thresholds"]["margin_threshold"] == 0.15


def test_routing_forensics_has_raw_margin_and_dept_scores():
    explanation = explain_routing(_auto_route_routing())
    forensics = explanation["forensics"]
    assert forensics["margin"] == 0.18
    assert forensics["entropy"] == 1.6
    departments = [item["department"] for item in forensics["top_department_scores"]]
    assert "Technical_Support" in departments and "IT_Support" in departments


def test_routing_controlled_review_classified_correctly():
    explanation = explain_routing(_forced_review_routing())
    assert explanation["evidence"]["gate_rule"] == "controlled_review"
    assert "human review" in explanation["plain"].lower()


def test_routing_escalation_override_surfaces_in_plain():
    routing = _auto_route_routing()
    routing["recommended_department"] = "Technical_Support"
    routing["department"] = "Escalation"
    explanation = explain_routing(routing)
    assert explanation["evidence"]["escalation_applied"] is True
    assert "Priority escalation" in explanation["plain"]


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


def test_duplicate_explanation_has_three_layers_when_duplicate():
    explanation = explain_duplicate(
        is_duplicate=True,
        duplicate_score=0.85,
        matched_text="production servers down",
        matched_id="f2bbf3c1",
        threshold=0.7623,
        duplicate_top_k=20,
    )
    assert explanation is not None
    assert "f2bbf3c1" in explanation["plain"]
    assert explanation["evidence"]["matched_text_original"] == "production servers down"
    assert explanation["evidence"]["signal"] == "faiss_cosine"
    assert explanation["forensics"]["retrieval_top_k"] == 20


def test_duplicate_explanation_none_when_not_duplicate_and_no_match():
    assert (
        explain_duplicate(
            is_duplicate=False,
            duplicate_score=0.0,
            matched_text=None,
            matched_id=None,
            threshold=0.7623,
            duplicate_top_k=20,
        )
        is None
    )


def test_duplicate_explanation_present_when_near_miss():
    explanation = explain_duplicate(
        is_duplicate=False,
        duplicate_score=0.71,
        matched_text="similar but below threshold",
        matched_id="abc",
        threshold=0.7623,
        duplicate_top_k=20,
    )
    assert explanation is not None
    assert "below the" in explanation["plain"]


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------


def test_priority_evidence_surfaces_matched_urgency_words():
    explanation = explain_priority(
        "the production server is down and is critical", "critical", 0.91
    )
    urgency = explanation["evidence"]["urgency_words"]
    assert "down" in urgency
    assert "critical" in urgency
    assert explanation["evidence"]["confidence"] == 0.91


def test_priority_evidence_does_not_match_substring_bug():
    # "download" must NOT count as the urgency word "down".
    explanation = explain_priority("please download the installer", "low", None)
    assert "down" not in explanation["evidence"]["urgency_words"]
    # `confidence` must be omitted, not invented, when None.
    assert "confidence" not in explanation["evidence"]


def test_priority_plain_describes_signal_source_when_no_cues():
    explanation = explain_priority("hi there please help", "medium", 0.55)
    assert "embedding signal only" in explanation["plain"]


def test_extract_with_evidence_returns_byte_identical_features():
    from backend.services.features import extract_handcrafted

    text = "the production server is down — please fix asap"
    features, _ = extract_handcrafted_with_evidence(text)
    assert features == extract_handcrafted(text)


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def test_build_ticket_explanation_composes_all_three():
    explanation = build_ticket_explanation(
        text="the server is down",
        routing=_auto_route_routing(),
        priority="high",
        priority_confidence=0.82,
        is_duplicate=True,
        duplicate_score=0.85,
        duplicate_matched_text="production servers down",
        duplicate_matched_id="f2bbf3c1",
        duplicate_threshold=0.7623,
    ).to_dict()
    assert set(explanation) == {"routing", "duplicate", "priority"}
    for layer in (explanation["routing"], explanation["duplicate"], explanation["priority"]):
        assert set(layer) == {"plain", "evidence", "forensics"}
