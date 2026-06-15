"""LLM provider interface and value types (Phase 8)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(RuntimeError):
    """A provider call failed (network, auth, rate limit, bad response)."""


class BudgetExceeded(RuntimeError):
    """A call was refused because it would exceed the configured token budget."""


@dataclass
class LLMRequest:
    user: str
    system: str = ""
    max_output_tokens: int = 512
    temperature: float = 0.3
    feature: str = "default"  # budget bucket / telemetry label


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    finish_reason: str | None = None
    fallback_used: bool = False

    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens) + int(self.completion_tokens)


@dataclass
class ModelPricing:
    """USD per 1M tokens."""

    input_per_m: float = 0.0
    output_per_m: float = 0.0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens / 1_000_000 * self.input_per_m
            + completion_tokens / 1_000_000 * self.output_per_m
        )


def estimate_tokens(text: str) -> int:
    """Cheap pre-call token estimate (~4 chars/token) for budget checks."""
    return max(1, len(str(text)) // 4)


class LLMProvider(ABC):
    name: str = "provider"
    model: str = "unknown"

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover
        ...

    @property
    def available(self) -> bool:
        """Whether this provider can actually be called (deps + credentials)."""
        return True
