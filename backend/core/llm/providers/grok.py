"""Grok (xAI) provider over the OpenAI-compatible REST API (Phase 8)."""

from __future__ import annotations

from ..base import LLMError, LLMProvider, LLMRequest, LLMResponse, ModelPricing

_ENDPOINT = "https://api.x.ai/v1/chat/completions"

# USD / 1M tokens — configurable; defaults are a conservative placeholder.
DEFAULT_PRICING = ModelPricing(input_per_m=0.30, output_per_m=0.50)


class GrokProvider(LLMProvider):
    name = "grok"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "grok-3-mini",
        timeout_s: float = 30.0,
        pricing: ModelPricing | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.pricing = pricing or DEFAULT_PRICING

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise LLMError("GROK_API_KEY / XAI_API_KEY is not configured.")
        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        try:
            response = httpx.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise LLMError(f"Grok call failed: {exc}") from exc

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
            finish = choice.get("finish_reason")
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Grok response: {data}") from exc

        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        return LLMResponse(
            text=(text or "").strip(),
            provider=self.name,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self.pricing.cost(prompt_tokens, completion_tokens),
            finish_reason=finish,
        )
