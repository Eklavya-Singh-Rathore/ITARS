"""AI-assistance layer (Phase 9) — grounded, advisory, off the routing path.

Composes the Phase-8 `LLMGateway` with the Phase-7 `RagService`. Every output is
grounded with retrieved evidence and exposes citations; recommendations require
retrieval above the confidence floor, otherwise return "insufficient evidence"
instead of generating. The routing decision is never produced or altered here,
and nothing is written to the database.
"""

from __future__ import annotations

from typing import Any

from ..core.config import SETTINGS, Settings
from ..core.llm.base import LLMError, LLMResponse


def _citations(rows: list[dict]) -> list[dict]:
    return [
        {
            "ticket_id": r.get("ticket_id"),
            "text": r.get("text"),
            "department": r.get("department"),
            "priority": r.get("priority"),
            "score": r.get("score"),
        }
        for r in (rows or [])
    ]


def _meta(response: LLMResponse) -> dict:
    return {
        "provider": response.provider,
        "model": response.model,
        "cost_usd": round(response.cost_usd, 6),
        "fallback_used": response.fallback_used,
        "tokens": response.total_tokens,
    }


class AssistantService:
    def __init__(self, *, llm, rag=None, settings: Settings = SETTINGS):
        self.llm = llm
        self.rag = rag
        self.settings = settings

    # ---------------------------------------------------------------- retrieval
    def _retrieve(self, text: str, *, exclude_ticket_id: str | None = None) -> list[dict]:
        if self.rag is None or not str(text).strip():
            return []
        try:
            return self.rag.similar_tickets(text, exclude_ticket_id=exclude_ticket_id)
        except Exception:
            return []  # graceful: retrieval down -> proceed ungrounded

    # ----------------------------------------------------------------- summary
    def summary(self, text: str, *, ticket_id: str | None = None) -> dict:
        citations = self._retrieve(text, exclude_ticket_id=ticket_id)
        try:
            response = self.llm.summarize(text, similar_tickets=citations or None)
        except LLMError as exc:
            return {
                "ai_assisted": False,
                "advisory": True,
                "text": "AI summary is unavailable right now.",
                "citations": _citations(citations),
                "error": str(exc),
            }
        return {
            "ai_assisted": True,
            "advisory": True,
            "text": response.text,
            "citations": _citations(citations),
            **_meta(response),
        }

    # ------------------------------------------------------------- explanation
    def explanation(self, *, department: str, route: str, explanation: dict[str, Any]) -> dict:
        try:
            response = self.llm.explain(
                department=department, route=route, explanation=explanation
            )
        except LLMError as exc:
            return {
                "ai_assisted": False,
                "advisory": True,
                "text": "AI explanation is unavailable right now.",
                "citations": [],
                "error": str(exc),
            }
        return {
            "ai_assisted": True,
            "advisory": True,
            "text": response.text,
            "citations": [],
            **_meta(response),
        }

    # ----------------------------------------------------------- recommendation
    def recommendation(
        self,
        *,
        ticket_text: str,
        routing: dict[str, Any],
        ticket_id: str | None = None,
    ) -> dict:
        """Review assistant — advisory only. Requires retrieval >= floor; otherwise
        returns insufficient_evidence rather than generating an ungrounded answer."""
        citations = self._retrieve(ticket_text, exclude_ticket_id=ticket_id)
        if not citations:
            return {
                "status": "insufficient_evidence",
                "advisory": True,
                "ai_assisted": False,
                "recommendation": None,
                "citations": [],
                "message": (
                    "No sufficiently similar resolved tickets were found. No "
                    "recommendation generated (advisory layer requires grounding)."
                ),
            }
        try:
            response = self.llm.recommend(
                ticket_text=ticket_text, routing=routing, similar_tickets=citations
            )
        except LLMError as exc:
            return {
                "status": "unavailable",
                "advisory": True,
                "ai_assisted": False,
                "recommendation": None,
                "citations": _citations(citations),
                "message": "AI recommendation is unavailable right now.",
                "error": str(exc),
            }
        return {
            "status": "ok",
            "advisory": True,
            "ai_assisted": True,
            "recommendation": response.text,
            "citations": _citations(citations),
            **_meta(response),
        }

    # ----------------------------------------------------------------- actions
    def actions(self, *, ticket_text: str, routing: dict[str, Any]) -> dict:
        """Suggested next actions for the agent (advisory; based on the ticket and
        the model's routing output)."""
        try:
            response = self.llm.suggest_actions(ticket_text=ticket_text, routing=routing)
        except LLMError as exc:
            return {
                "ai_assisted": False,
                "advisory": True,
                "text": "AI suggested actions are unavailable right now.",
                "citations": [],
                "error": str(exc),
            }
        return {
            "ai_assisted": True,
            "advisory": True,
            "text": response.text,
            "citations": [],
            **_meta(response),
        }

    # ------------------------------------------------------------------ health
    def health(self) -> dict:
        return {
            "llm": self.llm.health(),
            "rag_available": self.rag is not None,
            "retrieval_floor": self.settings.rag_score_floor,
        }
