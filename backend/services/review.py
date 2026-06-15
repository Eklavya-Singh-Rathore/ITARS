from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np


DEFAULT_TARGET_REVIEW_FRACTION = 0.15
DEFAULT_MIN_REVIEW_FRACTION = 0.10
DEFAULT_FALLBACK_THRESHOLD = 0.55


def build_default_review_policy(
    *,
    target_review_fraction: float = DEFAULT_TARGET_REVIEW_FRACTION,
    min_review_fraction: float = DEFAULT_MIN_REVIEW_FRACTION,
    fallback_threshold: float = DEFAULT_FALLBACK_THRESHOLD,
):
    target_review_fraction = float(
        np.clip(
            max(float(target_review_fraction), float(min_review_fraction)),
            0.0,
            1.0,
        )
    )
    fallback_threshold = float(np.clip(fallback_threshold, 0.0, 1.0))
    return {
        "target_review_fraction": target_review_fraction,
        "min_review_fraction": float(np.clip(min_review_fraction, 0.0, 1.0)),
        "fallback_threshold": fallback_threshold,
        "percentile_threshold": fallback_threshold,
        "effective_threshold": fallback_threshold,
        "percentile_review_fraction": target_review_fraction,
        "effective_review_fraction": target_review_fraction,
        "method": "percentile_plus_fixed_threshold",
        "fit_source": "default",
        "sample_size": 0,
    }


def select_review_indices_by_percentile(
    hybrid_confidences,
    *,
    target_review_fraction: float = DEFAULT_TARGET_REVIEW_FRACTION,
    min_review_fraction: float = DEFAULT_MIN_REVIEW_FRACTION,
):
    scores = np.asarray(hybrid_confidences, dtype=float).reshape(-1)
    if scores.size == 0:
        return np.zeros(0, dtype=bool)

    target_review_fraction = float(
        np.clip(
            max(float(target_review_fraction), float(min_review_fraction)),
            0.0,
            1.0,
        )
    )
    review_count = int(np.ceil(scores.size * target_review_fraction))
    review_count = max(review_count, int(np.ceil(scores.size * float(min_review_fraction))))
    review_count = min(review_count, scores.size)

    review_mask = np.zeros(scores.size, dtype=bool)
    if review_count == 0:
        return review_mask

    review_indices = np.argsort(scores, kind="mergesort")[:review_count]
    review_mask[review_indices] = True
    return review_mask


def fit_review_policy(
    hybrid_confidences,
    *,
    target_review_fraction: float = DEFAULT_TARGET_REVIEW_FRACTION,
    min_review_fraction: float = DEFAULT_MIN_REVIEW_FRACTION,
    fallback_threshold: float = DEFAULT_FALLBACK_THRESHOLD,
):
    scores = np.asarray(hybrid_confidences, dtype=float).reshape(-1)
    if scores.size == 0:
        return build_default_review_policy(
            target_review_fraction=target_review_fraction,
            min_review_fraction=min_review_fraction,
            fallback_threshold=fallback_threshold,
        )

    review_mask = select_review_indices_by_percentile(
        scores,
        target_review_fraction=target_review_fraction,
        min_review_fraction=min_review_fraction,
    )
    percentile_threshold = float(np.max(scores[review_mask])) if review_mask.any() else float(fallback_threshold)
    fallback_threshold = float(np.clip(fallback_threshold, 0.0, 1.0))
    effective_threshold = float(max(percentile_threshold, fallback_threshold))
    effective_review_mask = (scores <= percentile_threshold) | (scores < fallback_threshold)

    policy = build_default_review_policy(
        target_review_fraction=target_review_fraction,
        min_review_fraction=min_review_fraction,
        fallback_threshold=fallback_threshold,
    )
    policy.update(
        {
            "percentile_threshold": percentile_threshold,
            "effective_threshold": effective_threshold,
            "percentile_review_fraction": float(review_mask.mean()),
            "effective_review_fraction": float(effective_review_mask.mean()),
            "fit_source": "validation",
            "sample_size": int(scores.size),
            "hybrid_confidence_mean": float(np.mean(scores)),
            "hybrid_confidence_std": float(np.std(scores)),
            "hybrid_confidence_min": float(np.min(scores)),
            "hybrid_confidence_max": float(np.max(scores)),
        }
    )
    return policy


def load_review_policy(path, default=None):
    path = Path(path)
    if path.exists():
        loaded = joblib.load(path)
        if isinstance(loaded, dict):
            merged = build_default_review_policy()
            merged.update(loaded)
            return merged
    return default or build_default_review_policy()


def apply_controlled_review(mode, hybrid_confidence, review_policy=None):
    policy = review_policy or build_default_review_policy()
    hybrid_confidence = float(np.clip(hybrid_confidence, 0.0, 1.0))

    percentile_threshold = float(policy.get("percentile_threshold", DEFAULT_FALLBACK_THRESHOLD))
    fallback_threshold = float(policy.get("fallback_threshold", DEFAULT_FALLBACK_THRESHOLD))
    effective_threshold = float(policy.get("effective_threshold", max(percentile_threshold, fallback_threshold)))

    percentile_trigger = hybrid_confidence <= percentile_threshold
    fallback_trigger = hybrid_confidence < fallback_threshold
    forced_human_review = mode != "HUMAN_REVIEW" and (percentile_trigger or fallback_trigger)

    triggered_rules = []
    if percentile_trigger:
        triggered_rules.append("percentile")
    if fallback_trigger:
        triggered_rules.append("fixed_threshold")

    final_mode = "HUMAN_REVIEW" if forced_human_review else mode
    requires_review = final_mode != "AUTO_ROUTE"

    if forced_human_review:
        reason = (
            f"Controlled review injection forced HUMAN_REVIEW: hybrid_confidence={hybrid_confidence:.4f}, "
            f"percentile_threshold={percentile_threshold:.4f}, fallback_threshold={fallback_threshold:.4f}."
        )
    elif mode == "HUMAN_REVIEW":
        reason = "Two-stage gate already routed the ticket to HUMAN_REVIEW."
    elif mode == "AUTO_ROUTE_FLAGGED":
        reason = "Ticket remains AUTO_ROUTE_FLAGGED after the controlled review check."
    else:
        reason = "Ticket passed the controlled review check and remains AUTO_ROUTE."

    decision = {
        "base_mode": mode,
        "final_mode": final_mode,
        "requires_review": requires_review,
        "forced_human_review": forced_human_review,
        "triggered_rules": triggered_rules,
        "hybrid_confidence": hybrid_confidence,
        "percentile_threshold": percentile_threshold,
        "fallback_threshold": fallback_threshold,
        "effective_threshold": effective_threshold,
        "target_review_fraction": float(policy.get("target_review_fraction", DEFAULT_TARGET_REVIEW_FRACTION)),
        "reason": reason,
    }
    return final_mode, requires_review, decision
