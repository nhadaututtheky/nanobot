"""Token usage tracking and cost computation."""

from __future__ import annotations

# Pricing per 1M tokens: (input_cost_usd, output_cost_usd)
_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3": (2.0, 8.0),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    # DeepSeek
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    # Google
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    # Others
    "qwen-plus": (0.80, 2.0),
    "glm-4-plus": (0.70, 0.70),
    "moonshot-v1-128k": (0.84, 0.84),
}


def _find_pricing(model: str) -> tuple[float, float] | None:
    """Find pricing for a model by suffix matching."""
    # Exact match first
    if model in _PRICING:
        return _PRICING[model]
    # Strip provider prefix: "anthropic/claude-sonnet-4-6" -> "claude-sonnet-4-6"
    short = model.rsplit("/", 1)[-1] if "/" in model else model
    if short in _PRICING:
        return _PRICING[short]
    # Partial match: find longest matching suffix
    for key, pricing in _PRICING.items():
        if short.startswith(key) or key.startswith(short):
            return pricing
    return None


def compute_cost(model: str, usage: dict[str, int]) -> float:
    """Compute USD cost from model name and token counts.

    Returns 0.0 if model pricing is unknown.
    """
    pricing = _find_pricing(model)
    if not pricing:
        return 0.0
    input_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * pricing[0]
    output_cost = (usage.get("completion_tokens", 0) / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)
