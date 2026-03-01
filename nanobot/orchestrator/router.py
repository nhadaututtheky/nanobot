"""Model router — assigns the best available model to each task based on capability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.orchestrator.models import ModelCapability, TaskNode

if TYPE_CHECKING:
    from nanobot.config.schema import Config
    from nanobot.providers.registry import ProviderSpec

# Built-in defaults for common models.
# Users can override or extend via config.json → agents.orchestrator.models[]
DEFAULT_CAPABILITY_REGISTRY: tuple[ModelCapability, ...] = (
    # --- Anthropic ---
    ModelCapability(
        model="anthropic/claude-opus-4-5",
        provider="anthropic",
        capabilities=("reasoning", "coding", "creative", "data_analysis", "general"),
        tier="high",
        cost_input=15.0,
        cost_output=75.0,
        context_window=200_000,
    ),
    ModelCapability(
        model="anthropic/claude-sonnet-4-5",
        provider="anthropic",
        capabilities=("coding", "reasoning", "creative", "data_analysis", "general"),
        tier="mid",
        cost_input=3.0,
        cost_output=15.0,
        context_window=200_000,
    ),
    ModelCapability(
        model="anthropic/claude-haiku-3-5",
        provider="anthropic",
        capabilities=("research", "summarization", "translation", "general"),
        tier="low",
        cost_input=0.8,
        cost_output=4.0,
        context_window=200_000,
    ),
    # --- OpenAI ---
    ModelCapability(
        model="openai/gpt-4.1",
        provider="openai",
        capabilities=("reasoning", "coding", "creative", "data_analysis", "general"),
        tier="high",
        cost_input=2.0,
        cost_output=8.0,
        context_window=1_000_000,
    ),
    ModelCapability(
        model="openai/gpt-4.1-mini",
        provider="openai",
        capabilities=("coding", "research", "summarization", "general"),
        tier="mid",
        cost_input=0.4,
        cost_output=1.6,
        context_window=1_000_000,
    ),
    ModelCapability(
        model="openai/gpt-4.1-nano",
        provider="openai",
        capabilities=("research", "summarization", "translation", "general"),
        tier="low",
        cost_input=0.1,
        cost_output=0.4,
        context_window=1_000_000,
    ),
    # --- DeepSeek ---
    ModelCapability(
        model="deepseek/deepseek-chat",
        provider="deepseek",
        capabilities=("coding", "reasoning", "research", "general"),
        tier="mid",
        cost_input=0.27,
        cost_output=1.1,
        context_window=64_000,
    ),
    ModelCapability(
        model="deepseek/deepseek-reasoner",
        provider="deepseek",
        capabilities=("reasoning", "coding", "data_analysis"),
        tier="high",
        cost_input=0.55,
        cost_output=2.19,
        context_window=64_000,
    ),
    # --- Google ---
    ModelCapability(
        model="gemini/gemini-2.5-pro",
        provider="gemini",
        capabilities=("reasoning", "coding", "creative", "data_analysis", "general"),
        tier="high",
        cost_input=1.25,
        cost_output=10.0,
        context_window=1_000_000,
    ),
    ModelCapability(
        model="gemini/gemini-2.5-flash",
        provider="gemini",
        capabilities=("coding", "research", "summarization", "general"),
        tier="mid",
        cost_input=0.15,
        cost_output=0.6,
        context_window=1_000_000,
    ),
)

# Preferred tier for each capability type
CAPABILITY_TIER_PREFERENCE: dict[str, str] = {
    "reasoning": "high",
    "coding": "mid",
    "research": "low",
    "creative": "mid",
    "data_analysis": "mid",
    "translation": "low",
    "summarization": "low",
    "general": "mid",
}


class ModelRouter:
    """Route tasks to the best available model based on capability and cost."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._registry: list[ModelCapability] = []
        self._build_registry()

    def _build_registry(self) -> None:
        """Merge user-configured models with built-in defaults, then filter by availability."""
        orch_cfg = self._config.agents.orchestrator

        # User-configured models take priority
        if orch_cfg.models:
            for m in orch_cfg.models:
                self._registry.append(
                    ModelCapability(
                        model=m.model,
                        provider=m.provider,
                        capabilities=tuple(m.capabilities),
                        tier=m.tier,
                        cost_input=m.cost_input,
                        cost_output=m.cost_output,
                        context_window=m.context_window,
                    )
                )

        # Append built-in defaults (user entries shadow by model name)
        user_models = {m.model for m in self._registry}
        for default in DEFAULT_CAPABILITY_REGISTRY:
            if default.model not in user_models:
                self._registry.append(default)

        # Detect active providers + gateways, filter to reachable models
        self._active_providers = self._scan_active_providers()
        self._active_gateways = self._scan_active_gateways()
        self._registry = self._get_available_models()

        if not self._registry:
            logger.warning("No models available for orchestrator — using smart fallback")
            self._registry = list(self._smart_fallback())

        # Always ensure the currently active model is in the registry.
        # This handles providers not in the built-in defaults (dashscope, together, etc.)
        self._ensure_active_model_in_registry()

        logger.info(
            "Orchestrator registry: {} model(s) via {} provider(s) + {} gateway(s)",
            len(self._registry),
            len(self._active_providers),
            len(self._active_gateways),
        )

    def _scan_active_providers(self) -> set[str]:
        """Detect standard providers that have API keys configured."""
        from nanobot.providers.registry import PROVIDERS

        active: set[str] = set()
        for spec in PROVIDERS:
            if spec.is_gateway or spec.is_local or spec.is_oauth or spec.is_direct:
                continue
            p = getattr(self._config.providers, spec.name, None)
            if p and p.api_key:
                active.add(spec.name)
        return active

    def _scan_active_gateways(self) -> list[ProviderSpec]:
        """Detect gateway providers (OpenRouter, AiHubMix, etc.) with API keys."""
        from nanobot.providers.registry import PROVIDERS

        gateways: list[ProviderSpec] = []
        for spec in PROVIDERS:
            if not spec.is_gateway:
                continue
            p = getattr(self._config.providers, spec.name, None)
            if p and p.api_key:
                gateways.append(spec)
        return gateways

    def _get_available_models(self) -> list[ModelCapability]:
        """Filter registry to models reachable via active providers or gateways.

        A model is available if:
        1. Its provider has an API key (standard match), OR
        2. Any active gateway can route it (gateways route any model)
        """
        has_gateway = len(self._active_gateways) > 0
        available: list[ModelCapability] = []
        seen: set[str] = set()

        for mc in self._registry:
            if mc.model in seen:
                continue

            # Direct provider match
            if mc.provider in self._active_providers:
                available.append(mc)
                seen.add(mc.model)
                continue

            # Gateway can route any model
            if has_gateway:
                available.append(mc)
                seen.add(mc.model)

        return available

    def _ensure_active_model_in_registry(self) -> None:
        """Guarantee the user's currently active model appears in the registry.

        If the active provider/model isn't already covered (e.g. dashscope,
        together, custom providers), inject it as the highest-tier entry so the
        orchestrator actually uses the model the user has selected.
        """
        active_model = self._config.agents.defaults.model
        active_provider = self._config.agents.defaults.provider

        if not active_model:
            return

        # Already present?
        if any(m.model == active_model for m in self._registry):
            return

        logger.info(
            "Injecting active model {} ({}) into orchestrator registry",
            active_model,
            active_provider,
        )
        self._registry.insert(
            0,
            ModelCapability(
                model=active_model,
                provider=active_provider or "auto",
                capabilities=(
                    "reasoning",
                    "coding",
                    "research",
                    "creative",
                    "data_analysis",
                    "summarization",
                    "general",
                ),
                tier="high",  # treat the user's chosen model as highest priority
            ),
        )

    def _smart_fallback(self) -> tuple[ModelCapability, ...]:
        """Auto-generate entries when no models are available.

        If Anthropic key exists → split into Opus/Sonnet/Haiku tiers.
        Otherwise try the default model as a single mid-tier entry.
        """
        anthropic = self._config.providers.anthropic
        if anthropic.api_key:
            return (
                ModelCapability(
                    model="anthropic/claude-opus-4-5",
                    provider="anthropic",
                    capabilities=("reasoning", "coding", "creative", "data_analysis", "general"),
                    tier="high",
                    cost_input=15.0,
                    cost_output=75.0,
                ),
                ModelCapability(
                    model="anthropic/claude-sonnet-4-5",
                    provider="anthropic",
                    capabilities=("coding", "reasoning", "creative", "general"),
                    tier="mid",
                    cost_input=3.0,
                    cost_output=15.0,
                ),
                ModelCapability(
                    model="anthropic/claude-haiku-3-5",
                    provider="anthropic",
                    capabilities=("research", "summarization", "translation", "general"),
                    tier="low",
                    cost_input=0.8,
                    cost_output=4.0,
                ),
            )

        # Last resort: use default model as high-tier with full capabilities
        default_model = self._config.agents.defaults.model
        return (
            ModelCapability(
                model=default_model,
                provider=self._config.agents.defaults.provider or "auto",
                capabilities=(
                    "reasoning", "coding", "research", "creative",
                    "data_analysis", "summarization", "general",
                ),
                tier="high",
            ),
        )

    def route(self, task: TaskNode) -> ModelCapability:
        """Select the best model for a given task node."""
        cap = task.capability.value
        preferred_tier = CAPABILITY_TIER_PREFERENCE.get(cap, "mid")

        # Filter models that have this capability
        capable = [m for m in self._registry if cap in m.capabilities]
        if not capable:
            # Fallback: any model with "general" capability
            capable = [m for m in self._registry if "general" in m.capabilities]
        if not capable:
            capable = list(self._registry)
        if not capable:
            # Should not happen after _build_registry, but be safe
            return ModelCapability(
                model=self._config.agents.defaults.model,
                provider="auto",
                capabilities=("general",),
            )

        # Prefer the right tier
        tier_match = [m for m in capable if m.tier == preferred_tier]
        if tier_match:
            # Cheapest in the preferred tier
            return min(tier_match, key=lambda m: m.cost_input)

        # No exact tier match → closest tier, cheapest
        tier_order = {"high": 0, "mid": 1, "low": 2}
        pref_rank = tier_order.get(preferred_tier, 1)
        return min(
            capable, key=lambda m: (abs(tier_order.get(m.tier, 1) - pref_rank), m.cost_input)
        )

    def route_orchestrator(self) -> ModelCapability:
        """Select the strongest model for goal decomposition."""
        reasoning = [m for m in self._registry if "reasoning" in m.capabilities]
        high = [m for m in reasoning if m.tier == "high"]
        if high:
            return high[0]
        if reasoning:
            return reasoning[0]
        if self._registry:
            return self._registry[0]
        return ModelCapability(
            model=self._config.agents.defaults.model,
            provider="auto",
            capabilities=("general",),
        )

    def get_models_info(self) -> list[dict[str, Any]]:
        """Return serialisable info about available models."""
        gateway_names = [g.name for g in self._active_gateways]
        return [
            {
                "model": m.model,
                "provider": m.provider,
                "capabilities": list(m.capabilities),
                "tier": m.tier,
                "costInput": m.cost_input,
                "costOutput": m.cost_output,
                "contextWindow": m.context_window,
                "directAccess": m.provider in self._active_providers,
                "viaGateways": (gateway_names if m.provider not in self._active_providers else []),
            }
            for m in self._registry
        ]
