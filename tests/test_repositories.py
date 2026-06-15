"""Repository tests against in-memory SQLite (Phase 6)."""

from backend.repositories import tickets as repo


def _result(
    ticket_id: str, route: str, *, priority="high", dup=False, lang="en", conf=0.96
) -> dict:
    return {
        "ticket_id": ticket_id,
        "status": "DUPLICATE" if dup else "NOT DUPLICATE",
        "route": route,
        "department": "Technical_Support",
        "priority": priority,
        "priority_confidence": 0.82 if priority != "critical" else float("nan"),
        "confidence": conf,
        "review": route != "AUTO_ROUTE",
        "tags": "network_issue (0.93)",
        "message": "ok",
        "latency": 12.3,
        "is_duplicate": dup,
        "duplicate_score": 0.88 if dup else 0.2,
        "duplicate_text": "production servers down" if dup else None,
        "duplicate_matched_id": "f2bbf3c1" if dup else None,
        "explanation": "Ticket processed.",
        "explanation_struct": {
            "routing": {"plain": "p", "evidence": {}, "forensics": {}},
            "duplicate": None,
            "priority": {"plain": "p", "evidence": {}, "forensics": {}},
        },
        "original_text": f"text for {ticket_id}",
        "routing_text": f"text for {ticket_id}",
        "detected_language": lang,
        "translated_text": None,
        "translation_applied": False,
        "routing": {
            "recommended_department": "Technical_Support",
            "margin": 0.18,
            "entropy": 1.6,
            "top_tag_votes": [
                {"tag": "network_issue", "score": 0.93, "department": "Technical_Support"}
            ],
        },
    }


def test_save_analysis_and_list_recent(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("aaa11111", "AUTO_ROUTE"))
        repo.save_analysis(session, _result("bbb22222", "HUMAN_REVIEW", priority="critical"))
    with db_factory() as session:
        recent = repo.list_recent(session)
        assert {r["ticket_id"] for r in recent} == {"aaa11111", "bbb22222"}
        # Most recent first.
        assert recent[0]["ticket_id"] == "bbb22222"
        assert recent[0]["route"] == "HUMAN_REVIEW"


def test_human_review_enqueued_auto_route_not(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("auto0001", "AUTO_ROUTE"))
        repo.save_analysis(session, _result("rev00001", "HUMAN_REVIEW"))
        repo.save_analysis(session, _result("flag0001", "AUTO_ROUTE_FLAGGED"))
        queue = repo.list_review_queue(session)
        ids = {row["ticket_id"] for row in queue}
        assert ids == {"rev00001", "flag0001"}  # AUTO_ROUTE not enqueued


def test_review_queue_ordered_by_uncertainty(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("hi00conf", "HUMAN_REVIEW", conf=0.80))
        repo.save_analysis(session, _result("lo00conf", "HUMAN_REVIEW", conf=0.40))
        repo.save_analysis(session, _result("md00conf", "AUTO_ROUTE_FLAGGED", conf=0.60))
        queue = repo.list_review_queue(session)
        # Most uncertain (lowest confidence) first — not FIFO.
        assert [row["ticket_id"] for row in queue] == ["lo00conf", "md00conf", "hi00conf"]


def test_save_review_writes_feedback_and_resolves_queue(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("rev00002", "HUMAN_REVIEW"))
        result = repo.save_review(
            session,
            "rev00002",
            action="overridden",
            final_department="IT_Support",
            notes="actually an access issue",
        )
        assert result["final_department"] == "IT_Support"
        # Queue now empty (resolved).
        assert repo.list_review_queue(session) == []
        feedback = repo.list_feedback(session)
        assert len(feedback) == 1
        assert feedback[0]["predicted_department"] == "Technical_Support"
        assert feedback[0]["final_department"] == "IT_Support"
        assert feedback[0]["review_action"] == "overridden"


def test_escalate_routes_to_escalation(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("esc00001", "HUMAN_REVIEW"))
        result = repo.save_review(session, "esc00001", action="escalated")
        assert result["final_department"] == "Escalation"


def test_priority_confidence_nan_persisted_as_null(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("nan00001", "HUMAN_REVIEW", priority="critical"))
        detail = repo.get_by_id(session, "nan00001")
        assert detail["priority_confidence"] is None  # NaN -> None, not stored as text


def test_aggregate_metrics(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("m0000001", "AUTO_ROUTE", lang="en"))
        repo.save_analysis(session, _result("m0000002", "AUTO_ROUTE", lang="es"))
        repo.save_analysis(session, _result("m0000003", "HUMAN_REVIEW", lang="en"))
        repo.save_review(session, "m0000003", action="overridden", final_department="IT_Support")
        metrics = repo.aggregate_metrics(session)
        assert metrics["total_tickets"] == 3
        assert metrics["route_mode_counts"]["AUTO_ROUTE"] == 2
        assert metrics["route_mode_counts"]["HUMAN_REVIEW"] == 1
        assert metrics["language_counts"]["en"] == 2
        assert metrics["language_counts"]["es"] == 1
        assert metrics["feedback_total"] == 1
        assert metrics["override_rate"] == 1.0


def test_get_by_id_missing_returns_none(db_factory):
    with db_factory() as session:
        assert repo.get_by_id(session, "nope") is None


def test_feedback_correction_reason_and_stats(db_factory):
    with db_factory() as session:
        repo.save_analysis(session, _result("rev0fb01", "HUMAN_REVIEW"))
        repo.save_analysis(session, _result("rev0fb02", "HUMAN_REVIEW"))
        repo.save_review(
            session,
            "rev0fb01",
            action="overridden",
            final_department="IT_Support",
            correction_reason="wrong_department",
        )
        repo.save_review(session, "rev0fb02", action="approved")

        feedback = {f["ticket_id"]: f for f in repo.list_feedback(session)}
        assert feedback["rev0fb01"]["correction_reason"] == "wrong_department"
        assert feedback["rev0fb02"]["correction_reason"] is None

        stats = repo.feedback_stats(session)
        assert stats["total"] == 2
        assert stats["overrides"] == 1
        assert stats["department_changes"] == 1
        assert stats["override_rate"] == 0.5
        assert stats["reason_counts"]["wrong_department"] == 1
