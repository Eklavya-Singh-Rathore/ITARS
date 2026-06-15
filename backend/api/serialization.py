"""Back-compat shim — canonical implementation now lives in core.serialization."""

from ..core.serialization import json_safe, safe_float

__all__ = ["json_safe", "safe_float"]
