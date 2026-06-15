"""LLMGateway — the single entry point the application uses (Phase 8).

Selects a provider by config, falls back through a configured order on failure,
enforces the token budget, and exposes the task methods the assistance layer
(Phase 9) will call. Swapping providers — including adding Claude Haiku later —
is a config change, never a code change in callers.
"""

from __future__ import annotations

from typing import Any

from ...core.config import SETTINGS, Settings
from .base import (
    BudgetExceeded,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    estimate_tokens,
)
from .budget import BudgetTracker
from .prompts import (
    build_actions,
    build_explanation,
    build_recommendation,
    build_summary,
)
from .providers import EchoProvider, GeminiProvider, GrokProvider


class LLMGateway:
    def __init__(
        self,
        settings: Settings = SETTINGS,
        *,
        providers: dict[str, LLMProvider] | None = None,
        primary: str | None = None,
        fallback: list[str] | None = None,
        budget: BudgetTracker | None = None,
    ):
        self.settings = settings
        self.providers = providers or self._default_providers(settings)
        self.primary = primary or settings.llm_provider
        self.fallback = (
            fallback
            if fallback is not None
            else [p.strip() for p in settings.llm_fallback.split(",") if p.strip()]
        )
        self.budget = budget or BudgetTracker(settings.llm_feature_token_budget)

    @staticmethod
    def _default_providers(settings: Settings) -> dict[str, LLMProvider]:
        return {
            "echo": EchoProvider(),
            "gemini": GeminiProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_s=settings.llm_timeout_s,
            ),
            "grok": GrokProvider(
                api_key=settings.grok_api_key,
                model=settings.grok_model,
                timeout_s=settings.llm_timeout_s,
            ),
        }

    def _order(self) -> list[str]:
        order = [self.primary]
        for name in self.fallback:
            if name not in order:
                order.append(name)
        return order

    # ----------------------------------------------------------- primitive
    def generate(
        self,
        system: str,
        user: str,
        *,
        feature: str = "default",
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        request = LLMRequest(
            user=user,
            system=system,
            max_output_tokens=max_output_tokens or self.settings.llm_max_output_tokens,
            temperature=(
                temperature if temperature is not None else self.settings.llm_temperature
            ),
            feature=feature,
        )
        # Budget check BEFORE the call (raises BudgetExceeded, not swallowed).
        self.budget.check(
            feature, estimate_tokens(system + user) + request.max_output_tokens
        )

        errors: list[str] = []
        for index, name in enumerate(self._order()):
            provider = self.providers.get(name)
            if provider is None:
                errors.append(f"{name}: unknown provider")
                continue
            if not provider.available:
                errors.append(f"{name}: unavailable")
                continue
            try:
                response = provider.generate(request)
            except LLMError as exc:
                errors.append(f"{name}: {exc}")
                continue
            response.fallback_used = index > 0
            self.budget.record(
                feature, response.total_tokens or request.max_output_tokens
            )
            return response

        raise LLMError("All LLM providers failed: " + "; ".join(errors))

    # ----------------------------------------------------------- task methods
    def summarize(
        self,
        ticket_text: str,
        *,
        similar_tickets: list[dict[str, Any]] | None = None,
        feature: str = "summary",
    ) -> LLMResponse:
        system, user = build_summary(ticket_text, similar_tickets=similar_tickets)
        return self.generate(system, user, feature=feature)

    def explain(
        self,
        *,
        department: str,
        route: str,
        explanation: dict[str, Any],
        feature: str = "explanation",
    ) -> LLMResponse:
        system, user = build_explanation(
            department=department, route=route, explanation=explanation
        )
        return self.generate(system, user, feature=feature)

    def recommend(
        self,
        *,
        ticket_text: str,
        routing: dict[str, Any],
        similar_tickets: list[dict[str, Any]] | None = None,
        feature: str = "recommendation",
    ) -> LLMResponse:
        system, user = build_recommendation(
            ticket_text=ticket_text, routing=routing, similar_tickets=similar_tickets
        )
        return self.generate(system, user, feature=feature)

    def suggest_actions(
        self, *, ticket_text: str, routing: dict[str, Any], feature: str = "actions"
    ) -> LLMResponse:
        system, user = build_actions(ticket_text=ticket_text, routing=routing)
        return self.generate(system, user, feature=feature)

    # ----------------------------------------------------------- health
    def health(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "fallback": self.fallback,
            "providers": {
                name: {"model": provider.model, "available": provider.available}
                for name, provider in self.providers.items()
            },
            "budget": {
                "feature_token_budget": self.budget.feature_token_budget,
                "used": self.budget.usage(),
            },
        }
