"""Monitoring-aggregate tests (Phase 12) against in-memory SQLite.

Covers the confidence histogram (the inert-gate visual), named gate-rule
counts read from the persisted explanation layers, per-department reroute
rates, the predicted->final override flow, and model-vs-reviewer agreement.
"""

from backend.repositories import tickets as repo


def _result(
    ticket_id: str,
    route: str,
    *,
    department: str = "Technical_Support",
    conf: float = 0.96,
    gate_rule: str = "margin_pass",
    priority: str = "high",
) -> dict:
    return {
        "ticket_id": ticket_id,
        "status": "NOT DUPLICATE",
        "route": route,
        "department": department,
        "priority": priority,
        "priority_confidence": 0.82,
        "confidence": conf,
        "review": route != "AUTO_ROUTE",
        "tags": "network_issue (0.93)",
        "message": "ok",
        "latency": 11.0,
        "is_duplicate": False,
        "duplicate_score": 0.2,
        "duplicate_text": None,
        "duplicate_matched_id": None,
        "explanation": "Ticket processed.",
        "explanation_struct": {
            "routing": {"plain": "p", "evidence": {"gate_rule": gate_rule}, "forensics": {}},
            "duplicate": None,
            "priority": {"plain": "p", "evidence": {}, "forensics": {}},
        },
        "original_text": f"text for {ticket_id}",
        "routing_text": f"text for {ticket_id}",
        "detected_language": "en",
        "translated_text": None,
        "translation_applied": False,
        "routing": {
            "recommended_department": department,
            "margin": 0.18,
            "entropy": 1.6,
            "top_tag_votes": [
                {"tag": "network_issue", "score": 0.93, "department": department}
            ],
        },
    }


def test_confidence_histogram_buckets_and_thresholds(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("auto0001", "AUTO_ROUTE", conf=0.96))
        repo.save_analysis(session, _result("rev00001", "HUMAN_REVIEW", conf=0.40))
        repo.save_analysis(session, _result("rev00002", "HUMAN_REVIEW", conf=0.74))
        m = repo.monitoring_metrics(session, bins=10)

    hist = m["confidence_histogram"]
    assert len(hist["bins"]) == 10
    # 0.96 -> bin 9 (0.9-1.0); 0.40 -> bin 4; 0.74 -> bin 7.
    assert hist["series"]["AUTO_ROUTE"][9] == 1
    assert hist["series"]["HUMAN_REVIEW"][4] == 1
    assert hist["series"]["HUMAN_REVIEW"][7] == 1
    assert sum(hist["series"]["AUTO_ROUTE"]) == 1
    assert sum(hist["series"]["HUMAN_REVIEW"]) == 2
    # Thresholds are surfaced for the reference lines.
    assert hist["thresholds"]["hybrid_floor"] == 0.45
    assert "flagged_hybrid_floor" in hist["thresholds"]


def test_confidence_value_at_one_lands_in_top_bin(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("perfect0", "AUTO_ROUTE", conf=1.0))
        m = repo.monitoring_metrics(session, bins=10)
    assert m["confidence_histogram"]["series"]["AUTO_ROUTE"][9] == 1


def test_gate_rule_counts_from_explanation_layers(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("g0000001", "AUTO_ROUTE", gate_rule="margin_pass"))
        repo.save_analysis(session, _result("g0000002", "AUTO_ROUTE", gate_rule="margin_pass"))
        repo.save_analysis(
            session, _result("g0000003", "HUMAN_REVIEW", gate_rule="stage_1_floor")
        )
        m = repo.monitoring_metrics(session)
    assert m["gate_rule_counts"] == {"margin_pass": 2, "stage_1_floor": 1}


def test_department_reroute_rates_and_predicted_vs_final(db_factory):
    with db_factory() as session:
        # Two Technical_Support predictions: one rerouted, one approved as-is.
        repo.save_analysis(session, _result("d0000001", "HUMAN_REVIEW", department="Technical_Support"))
        repo.save_analysis(session, _result("d0000002", "HUMAN_REVIEW", department="Technical_Support"))
        # One Billing prediction, escalated.
        repo.save_analysis(session, _result("d0000003", "HUMAN_REVIEW", department="Billing"))

        repo.save_review(session, "d0000001", action="overridden", final_department="IT_Support")
        repo.save_review(session, "d0000002", action="approved")
        repo.save_review(session, "d0000003", action="escalated")

        m = repo.monitoring_metrics(session)

    rates = {r["department"]: r for r in m["department_reroute_rates"]}
    assert rates["Technical_Support"]["total"] == 2
    assert rates["Technical_Support"]["overrides"] == 1
    assert rates["Technical_Support"]["changes"] == 1
    assert rates["Technical_Support"]["reroute_rate"] == 0.5
    assert rates["Billing"]["escalations"] == 1
    assert rates["Billing"]["reroute_rate"] == 1.0  # escalation reroutes to Escalation

    flow = {(f["predicted"], f["final"]): f["count"] for f in m["predicted_vs_final"]}
    assert flow[("Technical_Support", "IT_Support")] == 1
    assert flow[("Billing", "Escalation")] == 1
    # The approved-as-is review is not a flow link (department unchanged).
    assert ("Technical_Support", "Technical_Support") not in flow


def test_routing_accuracy_agreement(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("a0000001", "HUMAN_REVIEW"))
        repo.save_analysis(session, _result("a0000002", "HUMAN_REVIEW"))
        repo.save_analysis(session, _result("a0000003", "HUMAN_REVIEW"))
        repo.save_review(session, "a0000001", action="approved")  # agreement
        repo.save_review(session, "a0000002", action="overridden", final_department="IT_Support")
        repo.save_review(session, "a0000003", action="approved")  # agreement

        acc = repo.monitoring_metrics(session)["routing_accuracy"]
    assert acc["total_reviewed"] == 3
    assert acc["agreements"] == 2
    assert acc["changes"] == 1
    assert acc["agreement_rate"] == round(2 / 3, 4)


def test_empty_database_is_safe(db_factory):
    with db_factory() as session:
        m = repo.monitoring_metrics(session)
    assert m["total_tickets"] == 0
    assert m["gate_rule_counts"] == {}
    assert m["department_reroute_rates"] == []
    assert m["predicted_vs_final"] == []
    assert m["routing_accuracy"]["agreement_rate"] == 0.0
    # Histogram still has its bin scaffold, all zero.
    assert len(m["confidence_histogram"]["bins"]) == 10
    assert sum(m["confidence_histogram"]["series"]["AUTO_ROUTE"]) == 0
