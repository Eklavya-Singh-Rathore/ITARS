"""JSON-safety helpers — strip NaN/Inf and numpy scalars before serialization.

Shared by the API layer (response bodies) and the persistence layer (JSON
columns): the pipeline can emit `float('nan')` (e.g. priority_confidence) and
numpy scalar types inside nested dicts, and raw JSON of those breaks strict
parsers / SQLite JSON storage.
"""

from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any) -> float | None:
    """Return a finite float, or None for NaN/Inf/None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def json_safe(obj: Any) -> Any:
    """Recursively convert numpy scalars to Python types and NaN/Inf to None."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    item = getattr(obj, "item", None)
    if callable(item) and obj.__class__.__module__ == "numpy":
        return json_safe(item())
    return obj
