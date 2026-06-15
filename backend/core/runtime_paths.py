from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import yaml

from ..services.routing import DEFAULT_TAG_TO_DEPARTMENT


DEFAULT_DUPLICATE_THRESHOLD = 0.7623

DEFAULT_ROUTING_CONFIG = {
    "global_threshold": 0.35,
    "confidence_threshold": 0.45,
    "default_department": "Human_Review",
    "departments": dict(DEFAULT_TAG_TO_DEPARTMENT),
    "priority_escalation": {
        "critical": "Escalation",
        "high": None,
    },
}


def _resolve_base_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir is None:
        return Path(__file__).resolve().parent
    return Path(base_dir).resolve()


def resolve_model_dir(base_dir: str | Path | None = None) -> Path:
    root = _resolve_base_dir(base_dir)
    candidates = [
        root / "Models",
        root.parent / "Models",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_data_root(base_dir: str | Path | None = None) -> Path:
    root = _resolve_base_dir(base_dir)
    candidates = [
        root / "Datasets",
        root.parent / "Datasets",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_dataset_file(
    base_dir: str | Path | None,
    filename: str,
    *,
    prefer_processed: bool = True,
) -> Path:
    data_root = resolve_data_root(base_dir)
    ordered = []
    if prefer_processed:
        ordered.extend(
            [
                data_root / "Processed" / filename,
                data_root / filename,
            ]
        )
    else:
        ordered.extend(
            [
                data_root / filename,
                data_root / "Processed" / filename,
            ]
        )

    for candidate in ordered:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Dataset '{filename}' not found in deployment bundle. Checked: {ordered}"
    )


def load_model_config(base_dir: str | Path | None = None) -> dict[str, Any]:
    model_dir = resolve_model_dir(base_dir)
    config_path = model_dir / "model_config.pkl"
    if not config_path.exists():
        return {}
    loaded = joblib.load(config_path)
    return loaded if isinstance(loaded, dict) else {}


def resolve_model_reference(
    model_ref: str | Path | None,
    *,
    base_dir: str | Path | None = None,
    model_dir: str | Path | None = None,
    default: str | None = None,
) -> str:
    if model_ref in (None, ""):
        if default is None:
            raise FileNotFoundError("No model reference was provided.")
        return str(default)

    raw_value = str(model_ref)

    # ✅ FIX: Directly return Hugging Face repo IDs
    # (format: username/model_name)
    if isinstance(raw_value, str) and "/" in raw_value and not raw_value.startswith(("Models", ".", "/")):
        return raw_value

    raw_path = Path(raw_value)
    base_path = _resolve_base_dir(base_dir)
    model_path_root = Path(model_dir).resolve() if model_dir is not None else resolve_model_dir(base_path)

    candidates: list[Path] = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
        if "Models" in raw_path.parts:
            model_idx = raw_path.parts.index("Models")
            suffix_parts = raw_path.parts[model_idx + 1:]
            if suffix_parts:
                candidates.append(model_path_root.joinpath(*suffix_parts))
        candidates.append(model_path_root / raw_path.name)
        candidates.append(base_path / raw_path.name)
    else:
        candidates.extend(
            [
                raw_path,
                base_path / raw_path,
                model_path_root / raw_path,
                model_path_root / raw_path.name,
                base_path / raw_path.name,
            ]
        )

    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve() if candidate.exists() else candidate
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return str(candidate)

    if default is not None:
        return str(default)

    return raw_value

def _merge_routing_config(loaded: dict[str, Any] | None) -> dict[str, Any]:
    merged = {
        "global_threshold": DEFAULT_ROUTING_CONFIG["global_threshold"],
        "confidence_threshold": DEFAULT_ROUTING_CONFIG["confidence_threshold"],
        "default_department": DEFAULT_ROUTING_CONFIG["default_department"],
        "departments": dict(DEFAULT_ROUTING_CONFIG["departments"]),
        "priority_escalation": dict(DEFAULT_ROUTING_CONFIG["priority_escalation"]),
    }
    if not isinstance(loaded, dict):
        return merged

    for key in ("global_threshold", "confidence_threshold", "default_department"):
        if key in loaded:
            merged[key] = loaded[key]

    merged["departments"].update(loaded.get("departments") or {})
    merged["priority_escalation"].update(loaded.get("priority_escalation") or {})
    return merged


def load_routing_config(
    base_dir: str | Path | None = None,
) -> tuple[dict[str, Any], Path | None]:
    root = _resolve_base_dir(base_dir)
    model_dir = resolve_model_dir(root)
    candidates = [
        root / "config" / "routing_config.yaml",
        model_dir / "routing_config.yaml",
        root.parent / "config" / "routing_config.yaml",
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue
        with candidate.open("r", encoding="utf-8") as handle:
            return _merge_routing_config(yaml.safe_load(handle)), candidate

    return _merge_routing_config(None), None


def load_duplicate_threshold(base_dir: str | Path | None = None) -> float:
    model_dir = resolve_model_dir(base_dir)
    threshold_path = model_dir / "duplicate_thresholds.pkl"
    if threshold_path.exists():
        payload = joblib.load(threshold_path)
        if isinstance(payload, dict):
            try:
                return float(payload.get("duplicate_threshold", DEFAULT_DUPLICATE_THRESHOLD))
            except (TypeError, ValueError):
                pass
    return float(DEFAULT_DUPLICATE_THRESHOLD)


def load_metric_artifact(
    base_dir: str | Path | None,
    filename: str,
) -> dict[str, Any]:
    model_dir = resolve_model_dir(base_dir)
    artifact_path = model_dir / filename
    if not artifact_path.exists():
        raise FileNotFoundError(f"Metric artifact not found: {artifact_path}")
    with artifact_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
