"""Feedback service (Phase 11) — persist human corrections and feed the loop.

Wraps the persistence-layer `save_review` and, on a correction (override /
escalate), surfaces the human-verified routing into the RAG `feedback_records`
collection so future retrieval and AI assistance can learn from real corrections.
RAG ingestion is best-effort and never blocks the persisted decision.
"""

from __future__ import annotations

from ..rag.schema import FEEDBACK_RECORDS
from ..repositories import tickets as ticket_repo


def record_review(
    session,
    ticket_id: str,
    *,
    action: str,
    final_department: str | None = None,
    final_priority: str | None = None,
    notes: str | None = None,
    correction_reason: str | None = None,
    reviewer: str | None = None,
    rag=None,
) -> dict:
    result = ticket_repo.save_review(
        session,
        ticket_id,
        action=action,
        final_department=final_department,
        final_priority=final_priority,
        notes=notes,
        correction_reason=correction_reason,
        reviewer=reviewer,
    )

    # Feed corrections back into retrieval (the compounding asset). Approvals
    # confirm the model and don't add a corrected label, so only override/escalate
    # are ingested.
    if rag is not None and action in ("overridden", "escalated"):
        try:
            ticket = ticket_repo.get_by_id(session, ticket_id)
            text = (ticket or {}).get("original_text")
            if text:
                rag.ingest(
                    [
                        {
                            "ticket_id": ticket_id,
                            "text": text,
                            "department": result["final_department"],  # human-verified
                            "priority": result.get("final_priority"),
                            "tags": correction_reason,
                        }
                    ],
                    collection=FEEDBACK_RECORDS,
                )
        except Exception:
            pass  # never block the persisted review on a retrieval hiccup

    return result


def stats(session) -> dict:
    return ticket_repo.feedback_stats(session)
