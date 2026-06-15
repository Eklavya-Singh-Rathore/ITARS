"""Persistence operations for the decision log (Phase 6).

Pure functions over a SQLAlchemy Session. Reads return plain dicts (composed
inside the session) so callers never touch detached ORM instances.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.serialization import json_safe, safe_float
from .models import (
    AnalyticsEvent,
    DuplicateResult,
    Feedback,
    ReviewQueueItem,
    RoutingResult,
    Ticket,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- writes
def save_analysis(session: Session, result: dict) -> str:
    """Persist a pipeline result: ticket + routing + duplicate + analytics event,
    and enqueue for review when the mode is not AUTO_ROUTE. Idempotent on
    ticket_id (merge)."""
    routing = result.get("routing") or {}
    ticket_id = str(result["ticket_id"])

    session.merge(
        Ticket(
            ticket_id=ticket_id,
            original_text=result.get("original_text") or "",
            routing_text=result.get("routing_text") or result.get("original_text") or "",
            detected_language=result.get("detected_language"),
            translation_applied=bool(result.get("translation_applied", False)),
        )
    )

    session.add(
        RoutingResult(
            ticket_id=ticket_id,
            route=result["route"],
            department=result["department"],
            recommended_department=routing.get("recommended_department"),
            priority=result["priority"],
            priority_confidence=safe_float(result.get("priority_confidence")),
            hybrid_confidence=float(result.get("confidence", 0.0)),
            margin=float(routing.get("margin", 0.0)),
            entropy=float(routing.get("entropy", 0.0)),
            review=bool(result.get("review", False)),
            tags=result.get("tags", ""),
            tag_votes=json_safe(routing.get("top_tag_votes")),
            explanation=result.get("explanation", ""),
            explanation_layers=json_safe(result.get("explanation_struct")),
            routing=json_safe(routing),
            latency_ms=float(result.get("latency", 0.0)),
        )
    )

    session.add(
        DuplicateResult(
            ticket_id=ticket_id,
            is_duplicate=bool(result.get("is_duplicate", False)),
            duplicate_score=float(result.get("duplicate_score", 0.0)),
            matched_id=result.get("duplicate_matched_id"),
            matched_text=result.get("duplicate_text"),
            threshold=float(result.get("duplicate_threshold", 0.0)),
        )
    )

    session.add(
        AnalyticsEvent(
            event_type="ticket_analyzed",
            ticket_id=ticket_id,
            payload={
                "route": result["route"],
                "department": result["department"],
                "priority": result["priority"],
                "language": result.get("detected_language"),
                "is_duplicate": bool(result.get("is_duplicate", False)),
                "latency_ms": float(result.get("latency", 0.0)),
            },
        )
    )

    if result["route"] != "AUTO_ROUTE":
        session.merge(
            ReviewQueueItem(
                ticket_id=ticket_id, route=result["route"], status="pending"
            )
        )

    session.commit()
    return ticket_id


def save_review(
    session: Session,
    ticket_id: str,
    *,
    action: str,
    final_department: str | None = None,
    final_priority: str | None = None,
    notes: str | None = None,
    correction_reason: str | None = None,
    reviewer: str | None = None,
) -> dict:
    """Record a human review decision: write feedback, resolve the queue item,
    log an analytics event."""
    routing = session.execute(
        select(RoutingResult)
        .where(RoutingResult.ticket_id == ticket_id)
        .order_by(RoutingResult.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if routing is None:
        raise KeyError(ticket_id)

    resolved_department = (
        "Escalation"
        if action == "escalated"
        else (final_department or routing.department)
    )
    resolved_priority = final_priority or routing.priority

    session.add(
        Feedback(
            ticket_id=ticket_id,
            predicted_department=routing.department,
            final_department=resolved_department,
            predicted_priority=routing.priority,
            final_priority=resolved_priority,
            review_action=action,
            correction_reason=correction_reason,
            review_notes=notes,
            reviewer=reviewer,
        )
    )

    queue_item = session.get(ReviewQueueItem, ticket_id)
    if queue_item is not None:
        queue_item.status = "resolved"
        queue_item.resolved_at = _utcnow()

    session.add(
        AnalyticsEvent(
            event_type="review_decision",
            ticket_id=ticket_id,
            payload={
                "action": action,
                "predicted_department": routing.department,
                "final_department": resolved_department,
            },
        )
    )
    session.commit()
    return {
        "ticket_id": ticket_id,
        "action": action,
        "final_department": resolved_department,
        "final_priority": resolved_priority,
        "correction_reason": correction_reason,
    }


# ---------------------------------------------------------------------- reads
def _latest_routing_map(session: Session, ticket_ids: list[str]) -> dict[str, RoutingResult]:
    if not ticket_ids:
        return {}
    rows = session.execute(
        select(RoutingResult)
        .where(RoutingResult.ticket_id.in_(ticket_ids))
        .order_by(RoutingResult.id.asc())
    ).scalars()
    # Last write wins per ticket.
    return {row.ticket_id: row for row in rows}


def _feedback_map(session: Session, ticket_ids: list[str]) -> dict[str, Feedback]:
    if not ticket_ids:
        return {}
    rows = session.execute(
        select(Feedback)
        .where(Feedback.ticket_id.in_(ticket_ids))
        .order_by(Feedback.id.asc())
    ).scalars()
    return {row.ticket_id: row for row in rows}


def _ticket_row(ticket: Ticket, routing: RoutingResult, feedback: Feedback | None) -> dict:
    return {
        "ticket_id": ticket.ticket_id,
        "original_text": ticket.original_text,
        "detected_language": ticket.detected_language,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "route": routing.route,
        "department": routing.department,
        "priority": routing.priority,
        "confidence": routing.hybrid_confidence,
        "is_duplicate": False,  # overridden from duplicate_results in list_recent
        "review_action": feedback.review_action if feedback else None,
        "final_department": feedback.final_department if feedback else None,
    }


def list_recent(session: Session, limit: int = 20) -> list[dict]:
    tickets = session.execute(
        select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
    ).scalars().all()
    ids = [t.ticket_id for t in tickets]
    routing_map = _latest_routing_map(session, ids)
    feedback_map = _feedback_map(session, ids)
    dup_ids = _duplicate_flags(session, ids)
    rows = []
    for ticket in tickets:
        routing = routing_map.get(ticket.ticket_id)
        if routing is None:
            continue
        row = _ticket_row(ticket, routing, feedback_map.get(ticket.ticket_id))
        row["is_duplicate"] = dup_ids.get(ticket.ticket_id, False)
        rows.append(row)
    return rows


def _duplicate_flags(session: Session, ticket_ids: list[str]) -> dict[str, bool]:
    if not ticket_ids:
        return {}
    rows = session.execute(
        select(DuplicateResult.ticket_id, DuplicateResult.is_duplicate).where(
            DuplicateResult.ticket_id.in_(ticket_ids)
        )
    ).all()
    return {tid: bool(flag) for tid, flag in rows}


def get_by_id(session: Session, ticket_id: str) -> dict | None:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        return None
    routing = session.execute(
        select(RoutingResult)
        .where(RoutingResult.ticket_id == ticket_id)
        .order_by(RoutingResult.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    duplicate = session.execute(
        select(DuplicateResult)
        .where(DuplicateResult.ticket_id == ticket_id)
        .order_by(DuplicateResult.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    feedback = session.execute(
        select(Feedback)
        .where(Feedback.ticket_id == ticket_id)
        .order_by(Feedback.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "ticket_id": ticket.ticket_id,
        "original_text": ticket.original_text,
        "routing_text": ticket.routing_text,
        "detected_language": ticket.detected_language,
        "translation_applied": ticket.translation_applied,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "route": routing.route if routing else None,
        "department": routing.department if routing else None,
        "priority": routing.priority if routing else None,
        "priority_confidence": routing.priority_confidence if routing else None,
        "confidence": routing.hybrid_confidence if routing else None,
        "tags": routing.tags if routing else None,
        "tag_votes": routing.tag_votes if routing else None,
        "explanation_layers": routing.explanation_layers if routing else None,
        "is_duplicate": duplicate.is_duplicate if duplicate else False,
        "duplicate_score": duplicate.duplicate_score if duplicate else 0.0,
        "duplicate_text": duplicate.matched_text if duplicate else None,
        "review_action": feedback.review_action if feedback else None,
        "final_department": feedback.final_department if feedback else None,
    }


def list_review_queue(session: Session, status: str = "pending") -> list[dict]:
    items = session.execute(
        select(ReviewQueueItem)
        .where(ReviewQueueItem.status == status)
        .order_by(ReviewQueueItem.enqueued_at.asc())
    ).scalars().all()
    ids = [item.ticket_id for item in items]
    routing_map = _latest_routing_map(session, ids)
    rows = []
    for item in items:
        ticket = session.get(Ticket, item.ticket_id)
        routing = routing_map.get(item.ticket_id)
        if ticket is None or routing is None:
            continue
        rows.append(
            {
                "ticket_id": item.ticket_id,
                "original_text": ticket.original_text,
                "route": routing.route,
                "department": routing.department,
                "priority": routing.priority,
                "confidence": routing.hybrid_confidence,
                "enqueued_at": item.enqueued_at.isoformat()
                if item.enqueued_at
                else None,
                "explanation_layers": routing.explanation_layers,
            }
        )
    # Active-learning ordering: most uncertain (lowest confidence) first, so
    # reviewer effort goes where it has the highest information value — not FIFO.
    rows.sort(key=lambda r: float(r["confidence"]))
    return rows


def list_feedback(session: Session, limit: int = 100) -> list[dict]:
    rows = session.execute(
        select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    ).scalars().all()
    out = []
    for fb in rows:
        ticket = session.get(Ticket, fb.ticket_id)
        out.append(
            {
                "ticket_id": fb.ticket_id,
                "original_text": ticket.original_text if ticket else None,
                "predicted_department": fb.predicted_department,
                "final_department": fb.final_department,
                "predicted_priority": fb.predicted_priority,
                "final_priority": fb.final_priority,
                "review_action": fb.review_action,
                "correction_reason": fb.correction_reason,
                "review_notes": fb.review_notes,
                "created_at": fb.created_at.isoformat() if fb.created_at else None,
            }
        )
    return out


def feedback_stats(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count(Feedback.id))) or 0
    overrides = (
        session.scalar(
            select(func.count(Feedback.id)).where(Feedback.review_action == "overridden")
        )
        or 0
    )
    escalations = (
        session.scalar(
            select(func.count(Feedback.id)).where(Feedback.review_action == "escalated")
        )
        or 0
    )
    dept_changes = (
        session.scalar(
            select(func.count(Feedback.id)).where(
                Feedback.final_department != Feedback.predicted_department
            )
        )
        or 0
    )
    reason_rows = session.execute(
        select(Feedback.correction_reason, func.count())
        .where(Feedback.correction_reason.is_not(None))
        .group_by(Feedback.correction_reason)
    ).all()
    return {
        "total": int(total),
        "overrides": int(overrides),
        "escalations": int(escalations),
        "department_changes": int(dept_changes),
        "override_rate": round(overrides / total, 4) if total else 0.0,
        "reason_counts": {str(k): int(v) for k, v in reason_rows if k is not None},
    }


def aggregate_metrics(session: Session) -> dict[str, Any]:
    total_tickets = session.scalar(select(func.count(Ticket.ticket_id))) or 0

    def _grouped(column) -> dict[str, int]:
        rows = session.execute(
            select(column, func.count()).group_by(column)
        ).all()
        return {str(key): int(count) for key, count in rows if key is not None}

    route_mode_counts = _grouped(RoutingResult.route)
    department_counts = _grouped(RoutingResult.department)
    priority_counts = _grouped(RoutingResult.priority)
    language_counts = _grouped(Ticket.detected_language)

    avg_latency = session.scalar(select(func.avg(RoutingResult.latency_ms))) or 0.0
    feedback_total = session.scalar(select(func.count(Feedback.id))) or 0
    overrides = (
        session.scalar(
            select(func.count(Feedback.id)).where(
                Feedback.review_action == "overridden"
            )
        )
        or 0
    )
    duplicate_total = (
        session.scalar(
            select(func.count(DuplicateResult.id)).where(
                DuplicateResult.is_duplicate.is_(True)
            )
        )
        or 0
    )

    return {
        "total_tickets": int(total_tickets),
        "route_mode_counts": route_mode_counts,
        "department_counts": department_counts,
        "priority_counts": priority_counts,
        "language_counts": language_counts,
        "avg_latency_ms": round(float(avg_latency), 2),
        "duplicate_total": int(duplicate_total),
        "feedback_total": int(feedback_total),
        "override_rate": round(overrides / feedback_total, 4) if feedback_total else 0.0,
    }


# --------------------------------------------------------- monitoring (Phase 12)
_HISTOGRAM_MODES = ("AUTO_ROUTE", "AUTO_ROUTE_FLAGGED", "HUMAN_REVIEW")


def monitoring_metrics(session: Session, *, bins: int = 10) -> dict[str, Any]:
    """Phase-12 monitoring aggregates that go beyond the four core distributions:

    * ``confidence_histogram`` — hybrid-confidence distribution bucketed into
      equal-width bins and split by routing mode, plus the gate thresholds so
      the UI can draw reference lines. This is the *inert-gate* visual: the
      audit found ``min(hybrid_confidence) ≈ 0.74`` so the Stage-1 floor (0.45)
      never fires — the bars all sit far to its right.
    * ``gate_rule_counts`` — how often each *named* gate rule fired
      (``margin_pass`` / ``entropy_pass`` / ``flagged_band`` / ``stage_1_floor`` /
      ``controlled_review`` …), read from the persisted explanation layers.
    * ``department_reroute_rates`` — per predicted-department, how often human
      review rerouted the ticket elsewhere (a live tag-map health monitor).
    * ``predicted_vs_final`` — the override flow (predicted → final), the input
      for a Sankey-style view. Only links where the department actually changed.
    * ``routing_accuracy`` — agreement between the model's department and the
      reviewer's final department, over all reviewed tickets.

    All feedback-derived panels are empty until reviewers act; the histogram
    populates as soon as any ticket is analyzed.
    """
    from ..core.config import SETTINGS

    bins = max(1, int(bins))

    # One pass over routing rows; keep the latest decision per ticket so a
    # re-analyzed ticket is not double-counted.
    rows = session.execute(
        select(
            RoutingResult.ticket_id,
            RoutingResult.route,
            RoutingResult.hybrid_confidence,
            RoutingResult.explanation_layers,
        ).order_by(RoutingResult.id.asc())
    ).all()
    latest: dict[str, tuple] = {tid: (route, conf, layers) for tid, route, conf, layers in rows}

    series = {mode: [0] * bins for mode in _HISTOGRAM_MODES}
    gate_rule_counts: dict[str, int] = {}

    def _bucket(value: float) -> int:
        idx = int(value * bins)
        return 0 if idx < 0 else (bins - 1 if idx >= bins else idx)

    for route, conf, layers in latest.values():
        value = float(conf or 0.0)
        value = 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)
        if route in series:
            series[route][_bucket(value)] += 1
        if isinstance(layers, dict):
            evidence = (layers.get("routing") or {}).get("evidence") or {}
            rule = evidence.get("gate_rule")
            if rule:
                gate_rule_counts[str(rule)] = gate_rule_counts.get(str(rule), 0) + 1

    edges = [round(i / bins, 4) for i in range(bins + 1)]
    histogram_bins = [
        {"lower": edges[i], "upper": edges[i + 1], "label": f"{edges[i]:.2f}"}
        for i in range(bins)
    ]

    # Feedback-derived: reroute rates, override flow, routing accuracy.
    feedback_rows = session.execute(
        select(
            Feedback.predicted_department,
            Feedback.final_department,
            Feedback.review_action,
        )
    ).all()

    dept: dict[str, dict[str, int]] = {}
    flow: dict[tuple[str, str], int] = {}
    total_reviewed = 0
    agreements = 0
    for predicted, final, action in feedback_rows:
        total_reviewed += 1
        key = predicted or "Unknown"
        bucket = dept.setdefault(
            key, {"total": 0, "overrides": 0, "escalations": 0, "changes": 0}
        )
        bucket["total"] += 1
        if action == "overridden":
            bucket["overrides"] += 1
        elif action == "escalated":
            bucket["escalations"] += 1
        if final and predicted and final != predicted:
            bucket["changes"] += 1
            flow[(key, final)] = flow.get((key, final), 0) + 1
        else:
            agreements += 1

    department_reroute_rates = sorted(
        (
            {
                "department": name,
                "total": v["total"],
                "overrides": v["overrides"],
                "escalations": v["escalations"],
                "changes": v["changes"],
                "reroute_rate": round(v["changes"] / v["total"], 4) if v["total"] else 0.0,
            }
            for name, v in dept.items()
        ),
        key=lambda r: (-r["reroute_rate"], -r["total"], r["department"]),
    )

    predicted_vs_final = sorted(
        ({"predicted": p, "final": f, "count": c} for (p, f), c in flow.items()),
        key=lambda r: (-r["count"], r["predicted"], r["final"]),
    )

    return {
        "total_tickets": int(session.scalar(select(func.count(Ticket.ticket_id))) or 0),
        "confidence_histogram": {
            "bins": histogram_bins,
            "series": series,
            "thresholds": {
                "hybrid_floor": round(float(SETTINGS.hybrid_floor), 4),
                "flagged_hybrid_floor": round(float(SETTINGS.flagged_hybrid_floor), 4),
            },
        },
        "gate_rule_counts": gate_rule_counts,
        "department_reroute_rates": list(department_reroute_rates),
        "predicted_vs_final": list(predicted_vs_final),
        "routing_accuracy": {
            "total_reviewed": int(total_reviewed),
            "agreements": int(agreements),
            "changes": int(total_reviewed - agreements),
            "agreement_rate": round(agreements / total_reviewed, 4) if total_reviewed else 0.0,
        },
    }
