"""Provider-agnostic LLM gateway (Phase 8).

The application only ever calls `LLMGateway` methods — never a provider directly —
so providers (Gemini, Grok, an offline Echo, or a future Claude Haiku) are
swappable purely by configuration. Includes budget caps and prompt-injection
fencing. LLMs assist; they never make the routing decision (Feature Report).
"""

from .base import BudgetExceeded, LLMError, LLMRequest, LLMResponse  # noqa: F401
from .gateway import LLMGateway  # noqa: F401
