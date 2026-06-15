"""Fatal artifact loading — no silent fallback (audit defects #1, #2).

The deployed loaders silently fell back to base `all-mpnet-base-v2` (and tolerated
missing files), so a degraded model set started without warning. Here, any missing
required artifact raises immediately, and the routing-label policy is validated on
load (`assert_valid_routing_label_policy`).

SBERT encoders are still resolved as Hugging Face Hub repo ids (the fine-tuned
weights are public: `Eklavya73/sbert_finetuned`, `Eklavya73/duplicate_sbert`); only
the local joblib/numpy artifacts are validated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib

from .config import MAIN_DIR, SETTINGS, Settings
from .runtime_paths import load_routing_config
from ..services.calibration import load_temperature_scaler
from ..services.review import load_review_policy
from ..services.routing import (
    DEFAULT_TAG_TO_DEPARTMENT,
    assert_valid_routing_label_policy,
    load_routing_label_policy,
)


@dataclass
class ArtifactBundle:
    model_dir: Path
    routing_config: dict
    routing_config_path: Path | None
    default_department: str
    priority_escalation: dict
    tag_model: object
    tag_calibrators: object
    temperature_scaler: dict
    tag_binarizer: object
    tag_list: list
    priority_model: object
    priority_encoder: object
    hf_scaler: object
    dept_prototypes: dict
    routing_label_policy: dict
    tag_to_department: dict
    review_policy: dict


def validate_artifacts(model_dir: Path, required: tuple[str, ...]) -> None:
    """Raise if any required artifact is absent — refuse to start degraded."""
    missing = [name for name in required if not (model_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"FATAL: {len(missing)} required serving artifact(s) missing from "
            f"{model_dir}: {missing}. Refusing to start with an incomplete model "
            "set (no silent fallback)."
        )


def load_artifacts(settings: Settings = SETTINGS) -> ArtifactBundle:
    model_dir = Path(settings.model_dir)
    validate_artifacts(model_dir, settings.required_artifacts)

    routing_config, routing_config_path = load_routing_config(MAIN_DIR)
    default_department = str(routing_config.get("default_department", "Human_Review"))
    priority_escalation = {
        str(priority).lower(): department
        for priority, department in (routing_config.get("priority_escalation") or {}).items()
    }

    tag_model = joblib.load(model_dir / "sbert_classifier.pkl")
    tag_calibrators = joblib.load(model_dir / "tag_calibrators.pkl")
    temperature_scaler = load_temperature_scaler(model_dir / "tag_temperature_scaler.pkl")
    tag_binarizer = joblib.load(model_dir / "mlb_tag_binarizer.pkl")
    tag_list = list(tag_binarizer.classes_)

    priority_bundle = joblib.load(model_dir / "tuned_priority_model.pkl")
    priority_model = (
        priority_bundle["model"]
        if isinstance(priority_bundle, dict) and "model" in priority_bundle
        else priority_bundle
    )
    priority_encoder = joblib.load(model_dir / "priority_encoder.pkl")
    hf_scaler = joblib.load(model_dir / "hf_scaler.pkl")

    dept_prototypes = joblib.load(model_dir / "department_prototypes.pkl")
    routing_label_policy = load_routing_label_policy(
        model_dir / "routing_label_policy.pkl",
        fallback_tag_to_department=routing_config.get(
            "departments", DEFAULT_TAG_TO_DEPARTMENT
        ),
        valid_tags=tag_list,
        valid_departments=dept_prototypes.keys(),
        default_department=default_department,
    )
    tag_to_department = routing_label_policy["tag_to_department"]
    assert_valid_routing_label_policy(
        routing_label_policy,
        valid_tags=tag_list,
        valid_departments=dept_prototypes.keys(),
    )

    review_policy = dict(load_review_policy(model_dir / "routing_review_policy.pkl"))
    if settings.apply_demo_review_cap:
        cap = float(settings.demo_review_threshold_cap)
        review_policy["percentile_threshold"] = min(
            float(review_policy.get("percentile_threshold", 0.55)), cap
        )
        review_policy["fallback_threshold"] = min(
            float(review_policy.get("fallback_threshold", 0.55)), cap
        )
        review_policy["effective_threshold"] = max(
            review_policy["percentile_threshold"],
            review_policy["fallback_threshold"],
        )

    return ArtifactBundle(
        model_dir=model_dir,
        routing_config=routing_config,
        routing_config_path=routing_config_path,
        default_department=default_department,
        priority_escalation=priority_escalation,
        tag_model=tag_model,
        tag_calibrators=tag_calibrators,
        temperature_scaler=temperature_scaler,
        tag_binarizer=tag_binarizer,
        tag_list=tag_list,
        priority_model=priority_model,
        priority_encoder=priority_encoder,
        hf_scaler=hf_scaler,
        dept_prototypes=dept_prototypes,
        routing_label_policy=routing_label_policy,
        tag_to_department=tag_to_department,
        review_policy=review_policy,
    )
