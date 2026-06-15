from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

try:
    from scipy.optimize import minimize_scalar
except Exception:  # pragma: no cover - scipy may be unavailable in some runtimes
    minimize_scalar = None


DEFAULT_EPS = 1e-6


def identity_temperature_scaler(eps: float = DEFAULT_EPS) -> dict:
    return {
        "temperature": 1.0,
        "eps": float(eps),
        "method": "logit_temperature_scaling",
        "fit_objective": "binary_nll",
        "fit_split": "validation",
        "base_calibration": "identity",
    }


def _ensure_2d(array_like) -> tuple[np.ndarray, bool]:
    arr = np.asarray(array_like, dtype=float)
    was_1d = arr.ndim == 1
    if was_1d:
        arr = arr.reshape(1, -1)
    return arr, was_1d


def _restore_shape(arr: np.ndarray, was_1d: bool) -> np.ndarray:
    if was_1d:
        return arr.reshape(-1)
    return arr


def _binary_nll(y_true, probs, eps: float = DEFAULT_EPS) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(probs, dtype=float), eps, 1.0 - eps)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def apply_per_class_calibration(raw_probs, calibrators=None):
    probs, was_1d = _ensure_2d(raw_probs)
    calibrated = probs.copy()

    if not calibrators:
        return _restore_shape(calibrated, was_1d)

    for idx, calibrator in enumerate(calibrators):
        if calibrator is None:
            continue

        values = calibrated[:, idx]
        if hasattr(calibrator, "predict"):
            calibrated[:, idx] = calibrator.predict(values)
        else:
            calibrated[:, idx] = calibrator.transform(values)

    return _restore_shape(calibrated, was_1d)


def apply_temperature_scaling(probabilities, temperature_scaler=None):
    probs, was_1d = _ensure_2d(probabilities)
    scaler = temperature_scaler or identity_temperature_scaler()

    temperature = float(scaler.get("temperature", 1.0))
    eps = float(scaler.get("eps", DEFAULT_EPS))
    temperature = max(temperature, eps)

    clipped = np.clip(probs, eps, 1.0 - eps)
    logits = np.log(clipped / (1.0 - clipped))
    scaled_logits = np.clip(logits / temperature, -50.0, 50.0)
    scaled = 1.0 / (1.0 + np.exp(-scaled_logits))

    return _restore_shape(scaled, was_1d)


def calibrate_probabilities(raw_probs, tag_calibrators=None, temperature_scaler=None):
    per_class = apply_per_class_calibration(raw_probs, tag_calibrators)
    return apply_temperature_scaling(per_class, temperature_scaler)


def max_confidence(probabilities) -> float:
    probs = np.asarray(probabilities, dtype=float)
    if probs.size == 0:
        return 0.0
    return float(np.max(probs))


def fit_temperature_scaler(validation_probs, y_true, bounds=(0.5, 5.0), eps: float = DEFAULT_EPS):
    probs, _ = _ensure_2d(validation_probs)
    y = np.asarray(y_true, dtype=float)
    if probs.shape != y.shape:
        raise ValueError(
            f"Shape mismatch for temperature scaling: probs={probs.shape}, y_true={y.shape}"
        )

    def objective(temp: float) -> float:
        scaled = apply_temperature_scaling(
            probs,
            {"temperature": temp, "eps": eps},
        )
        return _binary_nll(y, scaled, eps=eps)

    if minimize_scalar is not None:
        result = minimize_scalar(objective, bounds=bounds, method="bounded")
        best_temperature = float(result.x) if result.success else 1.0
    else:
        grid = np.exp(np.linspace(np.log(bounds[0]), np.log(bounds[1]), 256))
        losses = np.array([objective(float(temp)) for temp in grid], dtype=float)
        best_temperature = float(grid[int(losses.argmin())])

    best_temperature = max(best_temperature, eps)
    scaled = apply_temperature_scaling(
        probs,
        {"temperature": best_temperature, "eps": eps},
    )

    return {
        "temperature": round(best_temperature, 6),
        "eps": float(eps),
        "method": "logit_temperature_scaling",
        "fit_objective": "binary_nll",
        "fit_split": "validation",
        "base_calibration": "per_class_calibrator_then_temperature",
        "nll_before": _binary_nll(y, probs, eps=eps),
        "nll_after": _binary_nll(y, scaled, eps=eps),
        "mean_conf_before": float(np.mean(np.max(probs, axis=1))),
        "mean_conf_after": float(np.mean(np.max(scaled, axis=1))),
    }


def load_temperature_scaler(path, default=None):
    scaler_path = Path(path)
    if scaler_path.exists():
        loaded = joblib.load(scaler_path)
        if isinstance(loaded, dict):
            return loaded
        return {"temperature": float(loaded), "eps": DEFAULT_EPS}
    return default or identity_temperature_scaler()
