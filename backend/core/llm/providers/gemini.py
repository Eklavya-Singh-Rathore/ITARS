"""Gemini provider over the REST API (Phase 8) — httpx, no SDK dependency."""

from __future__ import annotations

from ..base import LLMError, LLMProvider, LLMRequest, LLMResponse, ModelPricing

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# USD / 1M tokens — Gemini 2.5 Flash (June 2026).
DEFAULT_PRICING = ModelPricing(input_per_m=0.30, output_per_m=2.50)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-2.5-flash",
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
            raise LLMError("GEMINI_API_KEY is not configured.")
        import httpx

        payload = {
            "system_instruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": {
                "maxOutputTokens": request.max_output_tokens,
                "temperature": request.temperature,
            },
        }
        try:
            response = httpx.post(
                _ENDPOINT.format(model=self.model),
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # network / auth / rate limit
            raise LLMError(f"Gemini call failed: {exc}") from exc

        try:
            candidate = data["candidates"][0]
            text = "".join(
                part.get("text", "") for part in candidate["content"]["parts"]
            )
            finish = candidate.get("finishReason")
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response: {data}") from exc

        usage = data.get("usageMetadata", {})
        prompt_tokens = int(usage.get("promptTokenCount", 0))
        completion_tokens = int(usage.get("candidatesTokenCount", 0))
        return LLMResponse(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self.pricing.cost(prompt_tokens, completion_tokens),
            finish_reason=finish,
        )
