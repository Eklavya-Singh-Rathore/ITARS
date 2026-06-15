"""ORM models for the ITARS decision log (Phase 6).

Replaces the v1 CSV log (which dropped `priority_confidence` and corrupts under
concurrent writes) with a normalized, queryable schema. Every routing decision,
duplicate verdict, review action, and analytics event is persisted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    original_text: Mapped[str] = mapped_column(Text, default="")
    routing_text: Mapped[str] = mapped_column(Text, default="")
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    translation_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class RoutingResult(Base):
    __tablename__ = "routing_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("tickets.ticket_id"), index=True
    )
    route: Mapped[str] = mapped_column(String(32), index=True)
    department: Mapped[str] = mapped_column(String(64), index=True)
    recommended_department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), index=True)
    priority_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    hybrid_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    margin: Mapped[float] = mapped_column(Float, default=0.0)
    entropy: Mapped[float] = mapped_column(Float, default=0.0)
    review: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(Text, default="")
    tag_votes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    explanation_layers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    routing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class DuplicateResult(Base):
    __tablename__ = "duplicate_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("tickets.ticket_id"), index=True
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("tickets.ticket_id"), index=True
    )
    predicted_department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    predicted_priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    final_priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review_action: Mapped[str] = mapped_column(String(16))  # approved|overridden|escalated
    correction_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("tickets.ticket_id"), primary_key=True
    )
    route: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
