"""Routing pipeline — ported from `hf_deploy/app.py` (the source of truth).

Preserves the deployed behavior exactly EXCEPT for the two sanctioned Phase-1
fixes:
  * priority features come from the canonical `extract_handcrafted` (skew fix);
  * all tuning constants come from `core.config.Settings` (one config source).

Gradio UI and CSV logging are intentionally dropped (Phase 2 API / Phase 6 DB).
`process_ticket` returns the full structured result, the routing detail, the
explanation string, and a `log_row` dict so no field is lost.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import numpy as np
from sentence_transformers import SentenceTransformer

from ..core.artifacts import ArtifactBundle, load_artifacts
from ..core.config import SETTINGS, Settings
from ..core.runtime_paths import load_model_config, resolve_model_reference
from .calibration import calibrate_probabilities
from .duplicates import CachedDuplicateDetectionEngine
from .explainability import build_ticket_explanation
from .features import extract_handcrafted
from .review import apply_controlled_review
from .routing import compute_department_hybrid_scores


def encode_ticket_embedding(text, encoder) -> np.ndarray:
    emb = np.asarray(encoder.encode(text), dtype=float).reshape(-1)
    emb_norm = np.linalg.norm(emb)
    if emb_norm == 0.0:
        return emb
    return emb / emb_norm


def compute_confidence_metrics(calibrated_probs) -> tuple[float, float]:
    probs = np.asarray(calibrated_probs, dtype=float).reshape(-1)
    if probs.size == 0:
        return 0.0, float("inf")

    sorted_probs = np.sort(probs)[::-1]
    top1 = float(sorted_probs[0])
    top2 = float(sorted_probs[1]) if len(sorted_probs) > 1 else 0.0
    margin = top1 - top2

    p = np.clip(probs, 1e-12, None)
    total = float(p.sum())
    if total == 0.0:
        p = np.full_like(p, 1.0 / len(p))
    else:
        p = p / total
    entropy = float(-np.sum(p * np.log(p)))
    return margin, entropy


class RoutingPipeline:
    """Deterministic ticket → routing-decision pipeline."""

    def __init__(
        self,
        settings: Settings = SETTINGS,
        *,
        artifacts: ArtifactBundle | None = None,
        translation_service=None,
        load_encoders: bool = True,
    ):
        self.settings = settings
        self.artifacts = artifacts if artifacts is not None else load_artifacts(settings)
        self.translation_service = translation_service
        # resolve_model_dir(base_dir) -> base_dir/Models == artifacts.model_dir
        self._base_dir = self.artifacts.model_dir.parent

        self.routing_sbert = None
        self.duplicate_sbert = None
        self.duplicate_engine = None
        if load_encoders:
            self._load_encoders()
            self.duplicate_engine = CachedDuplicateDetectionEngine(self._base_dir)

    # ------------------------------------------------------------------ setup
    def _load_encoders(self) -> None:
        model_config = load_model_config(self._base_dir)
        routing_ref = resolve_model_reference(
            model_config.get("sbert_model", self.settings.routing_sbert),
            base_dir=self._base_dir,
            model_dir=self.artifacts.model_dir,
        )
        duplicate_ref = resolve_model_reference(
            model_config.get("duplicate_sbert_model", self.settings.duplicate_sbert),
            base_dir=self._base_dir,
            model_dir=self.artifacts.model_dir,
            default=self.settings.sbert_fallback,
        )
        self.routing_sbert = SentenceTransformer(routing_ref)
        self.duplicate_sbert = (
            self.routing_sbert
            if duplicate_ref == routing_ref
            else SentenceTransformer(duplicate_ref)
        )

    # -------------------------------------------------------------- inference
    def predict_tags(self, text, emb):
        a = self.artifacts
        raw_probs = np.asarray(a.tag_model.predict_proba([emb])[0], dtype=float)
        calibrated = calibrate_probabilities(
            raw_probs,
            tag_calibrators=a.tag_calibrators,
            temperature_scaler=a.temperature_scaler,
        )
        top_idx = calibrated.argsort()[-5:][::-1]
        return top_idx, calibrated[top_idx], calibrated, raw_probs

    def predict_priority(self, text, emb, return_confidence: bool = False):
        a = self.artifacts
        features = extract_handcrafted(text)  # <-- skew fix: canonical training features
        features_scaled = a.hf_scaler.transform([features])
        x = np.hstack([emb.reshape(1, -1), features_scaled])
        pred_idx = int(a.priority_model.predict(x)[0])
        priority_label = str(a.priority_encoder.classes_[pred_idx])
        priority_confidence = float("nan")

        if hasattr(a.priority_model, "predict_proba"):
            try:
                probs = np.asarray(
                    a.priority_model.predict_proba(x)[0], dtype=float
                ).reshape(-1)
                if probs.size:
                    priority_confidence = float(probs[pred_idx])
            except Exception:
                priority_confidence = float("nan")

        if return_confidence:
            return priority_label, priority_confidence
        return priority_label

    def decide_routing_mode(self, hybrid_confidence, calibrated_probs):
        s = self.settings
        margin, entropy = compute_confidence_metrics(calibrated_probs)

        if hybrid_confidence < s.hybrid_floor:
            return "HUMAN_REVIEW", True, margin, entropy
        if (margin >= s.margin_threshold) or (entropy <= s.entropy_threshold):
            return "AUTO_ROUTE", False, margin, entropy
        if hybrid_confidence >= s.flagged_hybrid_floor:
            return "AUTO_ROUTE_FLAGGED", True, margin, entropy
        return "HUMAN_REVIEW", True, margin, entropy

    def route_ticket(self, emb, text) -> dict:
        a = self.artifacts
        s = self.settings
        _, _, calibrated_probs, _ = self.predict_tags(text, emb)
        best_dept, hybrid_confidence, department_details, top_tag_votes = (
            compute_department_hybrid_scores(
                calibrated_probs,
                emb,
                a.dept_prototypes,
                tag_to_department=a.tag_to_department,
                tag_names=a.tag_list,
                classifier_weight=s.hybrid_classifier_weight,
                similarity_weight=s.hybrid_similarity_weight,
                top_k=s.top_tags_k,
            )
        )
        priority, priority_confidence = self.predict_priority(
            text, emb, return_confidence=True
        )
        base_mode, _, margin, entropy = self.decide_routing_mode(
            hybrid_confidence, calibrated_probs
        )

        recommended_department = best_dept
        routed_department = recommended_department
        escalation_note = ""

        if not top_tag_votes or best_dept is None:
            review_decision = {
                "base_mode": "HUMAN_REVIEW",
                "final_mode": "HUMAN_REVIEW",
                "forced_human_review": False,
                "percentile_threshold": float(
                    a.review_policy.get("percentile_threshold", 0.55)
                ),
                "fallback_threshold": float(
                    a.review_policy.get("fallback_threshold", 0.55)
                ),
                "reason": "No valid tag votes or department resolved. Requires human review.",
            }
            return {
                "mode": "HUMAN_REVIEW",
                "department": a.default_department,
                "recommended_department": None,
                "priority": priority,
                "priority_confidence": priority_confidence,
                "hybrid_confidence": hybrid_confidence,
                "review": True,
                "margin": margin,
                "entropy": entropy,
                "best_details": {},
                "top_tag_votes": [],
                "review_decision": review_decision,
                "note": review_decision["reason"],
            }

        escalation_department = a.priority_escalation.get(str(priority).lower())
        if base_mode != "HUMAN_REVIEW" and escalation_department:
            routed_department = str(escalation_department)
            escalation_note = (
                f" Priority escalation override applied after gate: "
                f"{priority} -> {routed_department}."
            )

        mode, review, review_decision = apply_controlled_review(
            base_mode, hybrid_confidence, review_policy=a.review_policy
        )

        if review_decision.get("forced_human_review", False):
            final_department = a.default_department
            note = (
                f"{review_decision.get('reason', '')} "
                f"Recommended department before override: {routed_department}."
                f"{escalation_note}"
            ).strip()
        elif mode == "AUTO_ROUTE":
            final_department = routed_department
            note = (
                f"Stage 2 pass: hybrid_confidence={hybrid_confidence:.4f}, "
                f"margin={margin:.4f}, entropy={entropy:.4f}.{escalation_note}"
            )
        elif mode == "AUTO_ROUTE_FLAGGED":
            final_department = routed_department
            note = (
                f"Stage 2 flagged: hybrid_confidence={hybrid_confidence:.4f}, "
                f"margin={margin:.4f}, entropy={entropy:.4f}.{escalation_note}"
            )
        elif hybrid_confidence < s.hybrid_floor:
            final_department = a.default_department
            note = (
                f"Stage 1 reject: hybrid_confidence {hybrid_confidence:.4f} "
                f"< HYBRID_FLOOR {s.hybrid_floor}."
            )
        else:
            final_department = a.default_department
            note = (
                f"Stage 2 reject: hybrid_confidence={hybrid_confidence:.4f}, "
                f"margin={margin:.4f}, entropy={entropy:.4f}."
            )

        best_details = department_details.get(recommended_department, {})
        return {
            "mode": mode,
            "department": final_department,
            "recommended_department": recommended_department,
            "priority": priority,
            "priority_confidence": priority_confidence,
            "hybrid_confidence": hybrid_confidence,
            "review": review,
            "margin": margin,
            "entropy": entropy,
            "best_details": best_details,
            "department_details": department_details,
            "top_tag_votes": top_tag_votes,
            "review_decision": review_decision,
            "note": note.strip(),
        }

    def route_only(self, text: str) -> dict:
        """Routing decision only (no duplicate detection, no index registration)."""
        emb = encode_ticket_embedding(text, self.routing_sbert)
        return self.route_ticket(emb, text)

    def check_duplicate(self, text: str) -> dict:
        """Duplicate lookup only — returns the best match and threshold verdict."""
        emb = encode_ticket_embedding(text, self.duplicate_sbert)
        match = self.duplicate_engine.find_best_match(
            emb, k=self.settings.duplicate_top_k
        )
        threshold = float(self.duplicate_engine.duplicate_threshold)
        score = float(match["similarity"]) if match is not None else 0.0
        return {
            "is_duplicate": bool(match is not None and score >= threshold),
            "duplicate_score": round(score, 4),
            "matched_text": match.get("matched_text") if match is not None else None,
            "matched_id": match.get("ticket_id") if match is not None else None,
            "threshold": threshold,
        }

    # --------------------------------------------------------------- top-level
    def process_ticket(
        self, text: str, *, register: bool = True, translate: bool = True
    ) -> dict:
        t0 = time.time()
        ticket_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Stage 0 — translation. Route on the English text; preserve the original.
        original_text = str(text)
        translation = {
            "original_text": original_text,
            "detected_language": "en",
            "translated_text": original_text,
            "translation_applied": False,
            "model": None,
            "error": None,
        }
        if translate and self.translation_service is not None:
            translation = self.translation_service.translate(original_text)
        routing_text = translation.get("translated_text") or original_text

        routing_emb = encode_ticket_embedding(routing_text, self.routing_sbert)
        duplicate_emb = encode_ticket_embedding(routing_text, self.duplicate_sbert)

        best_match = self.duplicate_engine.find_best_match(
            duplicate_emb, k=self.settings.duplicate_top_k
        )
        dup_score = float(best_match["similarity"]) if best_match is not None else 0.0
        dup_text = best_match.get("matched_text") if best_match is not None else None
        dup_id = best_match.get("ticket_id") if best_match is not None else None
        is_dup = bool(
            best_match is not None
            and dup_score >= float(self.duplicate_engine.duplicate_threshold)
        )

        routing = self.route_ticket(routing_emb, routing_text)
        latency_ms = round((time.time() - t0) * 1000, 2)

        explanation_struct = build_ticket_explanation(
            text=routing_text,
            routing=routing,
            priority=routing["priority"],
            priority_confidence=(
                routing["priority_confidence"]
                if isinstance(routing["priority_confidence"], (int, float))
                and routing["priority_confidence"] == routing["priority_confidence"]  # NaN guard
                else None
            ),
            is_duplicate=is_dup,
            duplicate_score=dup_score,
            duplicate_matched_text=dup_text,
            duplicate_matched_id=dup_id,
            duplicate_threshold=float(self.duplicate_engine.duplicate_threshold),
            settings=self.settings,
        ).to_dict()

        mode = routing["mode"]
        dept = routing["department"]
        priority = routing["priority"]
        priority_confidence = routing["priority_confidence"]
        hybrid_confidence = routing["hybrid_confidence"]
        review = routing["review"]
        margin = routing["margin"]
        entropy = routing["entropy"]
        best_details = routing["best_details"]
        top_tag_votes = routing["top_tag_votes"]
        review_decision = routing["review_decision"]
        note = routing["note"]

        classifier_confidence = float(best_details.get("classifier_confidence", 0.0))
        semantic_similarity = float(best_details.get("semantic_similarity", 0.0))
        raw_semantic_similarity = float(best_details.get("raw_semantic_similarity", 0.0))
        base_mode = str(review_decision.get("base_mode", mode))
        review_reason = str(review_decision.get("reason", note))
        percentile_threshold = float(
            review_decision.get(
                "percentile_threshold",
                self.artifacts.review_policy.get("percentile_threshold", 0.55),
            )
        )
        fallback_threshold = float(
            review_decision.get(
                "fallback_threshold",
                self.artifacts.review_policy.get("fallback_threshold", 0.55),
            )
        )
        controlled_review_applied = bool(
            review_decision.get("forced_human_review", False)
        )
        recommended_department = routing.get("recommended_department")
        tag_summary = ", ".join(
            f"{vote['tag']} ({vote['score']:.2f})" for vote in top_tag_votes[:3]
        )
        recommended_text = (
            f" Recommended department before final policy: {recommended_department}."
            if recommended_department and recommended_department != dept
            else ""
        )

        if is_dup:
            explanation = (
                f"Duplicate detected (score={dup_score:.4f}). "
                f"Original: {str(dup_text)[:100]}. "
                f"Routing mode: {mode} (base_mode={base_mode}), "
                f"final_department={dept}, hybrid_confidence={hybrid_confidence:.3f}, "
                f"classifier_confidence={classifier_confidence:.3f}, "
                f"semantic_similarity={semantic_similarity:.3f} "
                f"(raw={raw_semantic_similarity:.3f}), margin={margin:.3f}, "
                f"entropy={entropy:.3f}, controlled_review_applied={controlled_review_applied}, "
                f"review_thresholds=(percentile={percentile_threshold:.3f}, "
                f"fallback={fallback_threshold:.3f}).{recommended_text} {note}"
            )
            status = "DUPLICATE"
            message = (
                f"Duplicate of: {str(dup_text)[:200]} (similarity={dup_score:.3f}). {note}"
            ).strip()
        else:
            explanation = (
                f"Ticket processed with final department {dept}. "
                f"Predicted tags [{tag_summary}] produced routing mode {mode} "
                f"(base_mode={base_mode}), hybrid_confidence={hybrid_confidence:.3f}, "
                f"classifier_confidence={classifier_confidence:.3f}, "
                f"semantic_similarity={semantic_similarity:.3f} "
                f"(raw={raw_semantic_similarity:.3f}), margin={margin:.3f}, "
                f"entropy={entropy:.3f}, controlled_review_applied={controlled_review_applied}, "
                f"review_thresholds=(percentile={percentile_threshold:.3f}, "
                f"fallback={fallback_threshold:.3f}).{recommended_text} {review_reason}"
            )
            status = "NOT DUPLICATE"
            message = note if note else "Ticket processed successfully"

        result = {
            "ticket_id": ticket_id,
            "status": status,
            "route": mode,
            "department": dept,
            "priority": priority,
            "priority_confidence": priority_confidence,
            "confidence": round(float(hybrid_confidence), 3),
            "review": review,
            "tags": tag_summary,
            "message": message,
            "latency": latency_ms,
            "is_duplicate": is_dup,
            "duplicate_score": round(float(dup_score), 4),
            "duplicate_text": dup_text,
            "duplicate_matched_id": dup_id,
            "duplicate_threshold": float(self.duplicate_engine.duplicate_threshold),
            "explanation": explanation,
            "explanation_struct": explanation_struct,
            "routing": routing,
            # --- translation (Phase 3): original preserved, routed on English ---
            "original_text": original_text,
            "routing_text": routing_text,
            "detected_language": translation.get("detected_language"),
            "translated_text": translation.get("translated_text"),
            "translation_applied": bool(translation.get("translation_applied", False)),
        }

        log_row = {
            "ticket_id": ticket_id,
            "timestamp": timestamp,
            "ticket_text": original_text,  # preserve the ORIGINAL text
            "detected_language": translation.get("detected_language"),
            "translation_applied": bool(translation.get("translation_applied", False)),
            "duplicate_flag": is_dup,
            "duplicate_score": round(float(dup_score), 4),
            "routing_mode": mode,
            "department": dept,
            "base_routing_mode": base_mode,
            "requires_review": bool(review),
            "controlled_review_applied": controlled_review_applied,
            "department_confidence": round(float(hybrid_confidence), 4),
            "classifier_confidence": round(float(classifier_confidence), 4),
            "semantic_similarity": round(float(semantic_similarity), 4),
            "raw_semantic_similarity": round(float(raw_semantic_similarity), 4),
            "priority": priority,
            "priority_confidence": (
                round(float(priority_confidence), 4)
                if np.isfinite(priority_confidence)
                else ""
            ),
            "selected_tags": tag_summary,
            "routing_score": round(float(hybrid_confidence), 4),
            "hybrid_confidence": round(float(hybrid_confidence), 4),
            "margin": round(float(margin), 4),
            "entropy": round(float(entropy), 4),
            "review_percentile_threshold": round(float(percentile_threshold), 4),
            "review_fallback_threshold": round(float(fallback_threshold), 4),
            "prediction_latency_ms": latency_ms,
            "explanation": explanation,
        }
        result["log_row"] = log_row

        if register:
            # Register the English (routing) text so it stays aligned with its embedding.
            self.duplicate_engine.add_ticket(
                ticket_id, routing_text, embedding=duplicate_emb
            )

        return result
