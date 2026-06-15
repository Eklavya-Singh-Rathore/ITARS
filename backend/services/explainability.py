"""Structured explanation builder (Phase 5).

Turns the routing pipeline's raw structured dict into a **layered** explanation
for every ticket — not just the human-review ones. Three layers, role-gated by
the frontend:

  * `plain`     — one human-readable sentence ("Routed to X because ...").
  * `evidence`  — bars, tag votes, top department scores, which gate rule
                  fired, urgency/negation keywords matched. The agent's
                  working layer.
  * `forensics` — raw margin/entropy/per-dept scores/policy version. Hidden
                  from agents by default; surfaced for admins/auditors.

Audit-driven fixes folded in here:
  * preserve & surface ORIGINAL text in the duplicate explanation
    (never the preprocessed/lemmatized text the v1 demo printed);
  * never report a confidence number for a prediction it does not belong to
    (priority confidence is reported only when the model actually produced
    one — otherwise the layer omits it);
  * the gate decision exposes WHICH rule fired in named terms
    (`stage_1_floor`, `margin_pass`, `entropy_pass`, `flagged_band`,
    `controlled_review`) rather than the v1 "Stage 2 pass" prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.config import SETTINGS, Settings
from .features import extract_handcrafted_with_evidence

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _classify_gate_rule(routing: dict, settings: Settings) -> str:
    """Name the gate rule that produced the final routing mode."""
    review = routing.get("review_decision") or {}
    if review.get("forced_human_review"):
        return "controlled_review"
    mode = routing.get("mode")
    hybrid = float(routing.get("hybrid_confidence", 0.0))
    margin = float(routing.get("margin", 0.0))
    entropy = float(routing.get("entropy", float("inf")))
    if mode == "HUMAN_REVIEW" and hybrid < settings.hybrid_floor:
        return "stage_1_floor"
    if mode == "AUTO_ROUTE":
        if margin >= settings.margin_threshold:
            return "margin_pass"
        if entropy <= settings.entropy_threshold:
            return "entropy_pass"
        return "auto_route"
    if mode == "AUTO_ROUTE_FLAGGED":
        return "flagged_band"
    return "human_review"


def _format_top_tags(votes: list[dict], k: int = 3) -> list[dict]:
    return [
        {"tag": str(v["tag"]), "score": round(float(v["score"]), 3), "department": str(v["department"])}
        for v in (votes or [])[:k]
    ]


def _top_department_scores(routing: dict, k: int = 5) -> list[dict]:
    """Best-effort: many `route_ticket` calls return only `best_details`; if the
    full per-department detail dict is present (forensics path), use it.
    """
    details = routing.get("department_details") or {}
    if not isinstance(details, dict):
        return []
    ranked = sorted(
        details.values(),
        key=lambda detail: float(detail.get("hybrid_confidence", 0.0)),
        reverse=True,
    )[:k]
    return [
        {
            "department": str(item.get("department")),
            "hybrid_confidence": round(float(item.get("hybrid_confidence", 0.0)), 3),
            "classifier_confidence": round(float(item.get("classifier_confidence", 0.0)), 3),
            "semantic_similarity": round(float(item.get("semantic_similarity", 0.0)), 3),
        }
        for item in ranked
    ]


def explain_routing(routing: dict, *, settings: Settings = SETTINGS) -> dict:
    department = routing.get("department")
    recommended = routing.get("recommended_department")
    top_votes = _format_top_tags(routing.get("top_tag_votes") or [], k=3)
    gate_rule = _classify_gate_rule(routing, settings)
    review = routing.get("review_decision") or {}
    best_details = routing.get("best_details") or {}
    escalation_applied = bool(
        recommended and department and recommended != department
        and not review.get("forced_human_review")
    )

    # Plain prose
    if review.get("forced_human_review"):
        tag_summary = ", ".join(v["tag"] for v in top_votes) or "no confident tags"
        plain = (
            f"Sent to human review: model recommended {recommended.replace('_', ' ')} "
            f"based on {tag_summary}, but its confidence fell into the bottom "
            f"{int(round(float(review.get('target_review_fraction', 0.15)) * 100))}% "
            "of recent traffic."
        ) if recommended else (
            "Sent to human review because no department scored above the confidence floor."
        )
    elif routing.get("mode") == "AUTO_ROUTE_FLAGGED":
        tag_summary = ", ".join(v["tag"] for v in top_votes) or "the predicted tags"
        plain = (
            f"Auto-routed to {str(department).replace('_', ' ')} based on {tag_summary}, "
            f"but flagged for QA — top tags are close in score."
        )
    elif routing.get("mode") == "AUTO_ROUTE":
        tag_summary = ", ".join(v["tag"] for v in top_votes) or "the predicted tags"
        plain = (
            f"Auto-routed to {str(department).replace('_', ' ')} because {tag_summary} "
            f"map to that department with high confidence."
        )
    else:
        plain = "Sent to human review."

    if escalation_applied:
        plain += (
            f" Priority escalation rerouted from "
            f"{str(recommended).replace('_', ' ')} to "
            f"{str(department).replace('_', ' ')}."
        )

    evidence = {
        "department": department,
        "recommended_department": recommended,
        "tag_votes": top_votes,
        "gate_rule": gate_rule,
        "gate_reason": review.get("reason") or routing.get("note"),
        "hybrid_confidence": round(float(routing.get("hybrid_confidence", 0.0)), 4),
        "classifier_confidence": round(float(best_details.get("classifier_confidence", 0.0)), 4),
        "semantic_similarity": round(float(best_details.get("semantic_similarity", 0.0)), 4),
        "escalation_applied": escalation_applied,
        "thresholds": {
            "hybrid_floor": settings.hybrid_floor,
            "flagged_hybrid_floor": settings.flagged_hybrid_floor,
            "margin_threshold": settings.margin_threshold,
            "entropy_threshold": settings.entropy_threshold,
        },
    }

    forensics = {
        "margin": round(float(routing.get("margin", 0.0)), 6),
        "entropy": round(float(routing.get("entropy", 0.0)), 6),
        "raw_semantic_similarity": round(float(best_details.get("raw_semantic_similarity", 0.0)), 6),
        "weights": {
            "classifier_weight": settings.hybrid_classifier_weight,
            "similarity_weight": settings.hybrid_similarity_weight,
        },
        "review_decision": review,
        "top_department_scores": _top_department_scores(routing),
        "top_tag_votes_full": routing.get("top_tag_votes") or [],
    }
    return {"plain": plain, "evidence": evidence, "forensics": forensics}


# ---------------------------------------------------------------------------
# Duplicate
# ---------------------------------------------------------------------------


def explain_duplicate(
    *,
    is_duplicate: bool,
    duplicate_score: float,
    matched_text: str | None,
    matched_id: str | None,
    threshold: float,
    duplicate_top_k: int,
) -> dict | None:
    """None when nothing similar was found; otherwise a three-layer explanation.

    `matched_text` is the ORIGINAL stored text of the matched ticket (never the
    lemmatized form — v1 demo defect). Serving uses raw FAISS cosine over the
    duplicate-fine-tuned SBERT encoder, so the evidence layer reports a single
    similarity signal honestly rather than fabricating a hybrid breakdown.
    """
    score = float(duplicate_score)
    if matched_text is None and not is_duplicate:
        return None

    if is_duplicate:
        plain = (
            f"Matched an existing ticket (ID {matched_id}) with "
            f"cosine similarity {score:.3f}, above the {threshold:.3f} threshold."
        )
    else:
        plain = (
            f"No duplicate. Closest existing ticket scored {score:.3f}, "
            f"below the {threshold:.3f} threshold."
        )

    evidence = {
        "matched_id": matched_id,
        "matched_text_original": matched_text,
        "similarity": round(score, 4),
        "threshold": round(float(threshold), 4),
        "signal": "faiss_cosine",  # serving signal — honestly reported
        "is_duplicate": bool(is_duplicate),
    }
    forensics = {
        "retrieval_top_k": int(duplicate_top_k),
        "encoder_signal": "sbert_cosine_only",
        "note": (
            "Serving uses FAISS top-k cosine on the duplicate SBERT encoder. "
            "The training-time hybrid signals (lexical, cross-encoder, tag "
            "Jaccard) are documented in the duplicate engine but not run "
            "per-query in serving — keeps inference at ~1 ms."
        ),
    }
    return {"plain": plain, "evidence": evidence, "forensics": forensics}


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------


def explain_priority(
    text: str,
    priority: str,
    priority_confidence: float | None,
) -> dict:
    """Layered explanation of the priority prediction.

    Surfaces the urgency/negation keywords that actually fired (whole-word) —
    the model itself uses the COUNTS of these as features, so showing which
    words triggered them is faithful evidence.

    `priority_confidence` is included only when the model produced one; it is
    never invented (audit rule: don't display a confidence number against a
    prediction it does not belong to).
    """
    _, evidence_dict = extract_handcrafted_with_evidence(text)
    urgency = evidence_dict["urgency_words_matched"]
    negation = evidence_dict["negation_words_matched"]

    parts = [f"Predicted {priority} priority"]
    if urgency:
        parts.append(f"urgency cues: {', '.join(urgency)}")
    if negation:
        parts.append(f"negation cues: {', '.join(negation)}")
    if not urgency and not negation:
        parts.append("no explicit urgency/negation cues — based on embedding signal only")
    plain = "; ".join(parts) + "."

    evidence = {
        "priority": priority,
        "urgency_words": urgency,
        "negation_words": negation,
        "word_count": evidence_dict["word_count"],
        "char_length": evidence_dict["char_length"],
    }
    if priority_confidence is not None:
        evidence["confidence"] = round(float(priority_confidence), 4)

    forensics = {
        "handcrafted_features": {
            "char_length": evidence_dict["char_length"],
            "word_count": evidence_dict["word_count"],
            "vocab_richness": evidence_dict["vocab_richness"],
            "avg_word_length": evidence_dict["avg_word_length"],
            "urgency_count": evidence_dict["urgency_count"],
            "negation_count": evidence_dict["negation_count"],
        },
        "feature_source": "training-aligned (extract_handcrafted v2, skew fix)",
    }
    return {"plain": plain, "evidence": evidence, "forensics": forensics}


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


@dataclass
class TicketExplanation:
    routing: dict
    duplicate: dict | None
    priority: dict

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing": self.routing,
            "duplicate": self.duplicate,
            "priority": self.priority,
        }


def build_ticket_explanation(
    *,
    text: str,
    routing: dict,
    priority: str,
    priority_confidence: float | None,
    is_duplicate: bool,
    duplicate_score: float,
    duplicate_matched_text: str | None,
    duplicate_matched_id: str | None,
    duplicate_threshold: float,
    settings: Settings = SETTINGS,
) -> TicketExplanation:
    """Compose the three explanation panels for one ticket."""
    return TicketExplanation(
        routing=explain_routing(routing, settings=settings),
        duplicate=explain_duplicate(
            is_duplicate=is_duplicate,
            duplicate_score=duplicate_score,
            matched_text=duplicate_matched_text,
            matched_id=duplicate_matched_id,
            threshold=duplicate_threshold,
            duplicate_top_k=settings.duplicate_top_k,
        ),
        priority=explain_priority(text, priority, priority_confidence),
    )
