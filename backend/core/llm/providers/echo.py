"""Echo provider — deterministic, offline, zero-cost (Phase 8).

The default provider so the gateway works with no API keys: it returns a
predictable placeholder derived from the request. Lets the rest of the system
(Phase 9 assistance) be developed and tested without network or spend.
"""

from __future__ import annotations

from ..base import LLMProvider, LLMRequest, LLMResponse, estimate_tokens


class EchoProvider(LLMProvider):
    name = "echo"
    model = "echo-1"

    def generate(self, request: LLMRequest) -> LLMResponse:
        condensed = " ".join(str(request.user).split())
        text = f"[echo:{request.feature}] {condensed[:280]}"
        prompt_tokens = estimate_tokens(request.system + request.user)
        completion_tokens = estimate_tokens(text)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=0.0,
            finish_reason="stop",
        )
