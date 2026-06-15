"""In-process token budget tracker (Phase 8).

Guards against runaway LLM spend: each feature (summary, explanation, review,
…) has an output-token budget per process. `check` is called before a request
(refusing if the estimate would blow the cap) and `record` after, with actual
usage. A budget of 0 means unlimited.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from .base import BudgetExceeded


class BudgetTracker:
    def __init__(self, feature_token_budget: int = 0):
        self.feature_token_budget = int(feature_token_budget)
        self._used: dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def check(self, feature: str, estimated_tokens: int) -> None:
        if self.feature_token_budget <= 0:
            return
        with self._lock:
            projected = self._used[feature] + int(estimated_tokens)
        if projected > self.feature_token_budget:
            raise BudgetExceeded(
                f"LLM token budget exceeded for feature '{feature}': "
                f"{projected} > {self.feature_token_budget}."
            )

    def record(self, feature: str, tokens: int) -> None:
        with self._lock:
            self._used[feature] += int(tokens)

    def usage(self) -> dict[str, int]:
        with self._lock:
            return dict(self._used)
