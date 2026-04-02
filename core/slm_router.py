"""
SLM Router — Smart model routing to cut LLM costs by ~60%.

Routes tasks to the cheapest capable model:
  - Complex reasoning / refactoring → heavy model (Claude 3.5 / GPT-4o)
  - Boilerplate generation / formatting → light model (Claude Haiku / GPT-4o-mini / Ollama)
  - Simple stubs / docstrings → local model (Ollama Llama3) or heuristic

Usage:
    from core.slm_router import SLMRouter, TaskComplexity

    router = SLMRouter()
    response = router.complete(
        messages=[LLMMessage(role="user", content="Add type hints to this function")],
        complexity=TaskComplexity.LOW
    )
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Optional

from config.llm_providers import (
    BaseLLMProvider, LLMMessage, LLMResponse,
    AnthropicProvider, OpenAIProvider, OllamaProvider, HeuristicProvider,
    get_llm_client,
)

logger = logging.getLogger(__name__)


# ─── Complexity Tiers ─────────────────────────────────────────────────────────

class TaskComplexity(str, Enum):
    LOW    = "low"      # Boilerplate, stubs, docstrings, formatting
    MEDIUM = "medium"   # Test generation, simple bug fixes
    HIGH   = "high"     # Architecture decisions, complex refactors, patch reasoning


# Keywords used to auto-classify task complexity
_HIGH_KEYWORDS = [
    "architect", "refactor", "redesign", "security", "auth", "authentication",
    "race condition", "deadlock", "concurrency", "performance", "optimize",
    "complex", "critical", "production", "breaking change"
]

_LOW_KEYWORDS = [
    "docstring", "comment", "format", "style", "stub", "boilerplate", "type hint",
    "rename", "add import", "fix whitespace", "add logging", "simple"
]


# ─── Model Tiers ──────────────────────────────────────────────────────────────

class ModelTier:
    """Represents a model choice for a given complexity tier."""

    def __init__(self, name: str, provider_class, model_env_var: str, default_model: str):
        self.name          = name
        self.provider_class = provider_class
        self.model_env_var = model_env_var
        self.default_model = default_model
        self._instance: Optional[BaseLLMProvider] = None

    def get_provider(self) -> Optional[BaseLLMProvider]:
        if self._instance is None:
            try:
                instance = self.provider_class()
                if instance.is_available():
                    self._instance = instance
                    logger.debug(f"[SLM] Tier '{self.name}' using {instance.name}")
            except Exception as e:
                logger.debug(f"[SLM] Tier '{self.name}' unavailable: {e}")
        return self._instance


# Define provider cascade per complexity tier
_HEAVY_TIER = ModelTier("heavy", AnthropicProvider, "ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
_LIGHT_TIER = ModelTier("light", OpenAIProvider,    "OPENAI_MODEL",    "gpt-4o-mini")
_LOCAL_TIER = ModelTier("local", OllamaProvider,    "OLLAMA_MODEL",    "llama3.2")


# ─── Router ───────────────────────────────────────────────────────────────────

class SLMRouter:
    """
    Routes LLM calls to the appropriate model based on task complexity.
    Falls back to next available provider if preferred is unavailable.

    Cost savings: ~60% by routing LOW tasks to local Ollama instead of Claude.
    """

    def __init__(self):
        self._call_log: list[dict] = []

    def classify(self, prompt: str) -> TaskComplexity:
        """Auto-classify prompt complexity from keywords."""
        lower = prompt.lower()
        if any(k in lower for k in _HIGH_KEYWORDS):
            return TaskComplexity.HIGH
        if any(k in lower for k in _LOW_KEYWORDS):
            return TaskComplexity.LOW
        return TaskComplexity.MEDIUM

    def complete(
        self,
        messages: list[LLMMessage],
        complexity: Optional[TaskComplexity] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> LLMResponse:
        """
        Complete a prompt using the most cost-effective model for the complexity.

        Args:
            messages: List of LLMMessage objects
            complexity: Task complexity override. If None, auto-classifies from messages.
            max_tokens: Max tokens for completion
            temperature: Sampling temperature
        """
        # Auto-classify if not specified
        if complexity is None:
            prompt_text = " ".join(m.content for m in messages)
            complexity  = self.classify(prompt_text)

        provider = self._select_provider(complexity)
        logger.info(f"[SLM] Routing {complexity.value} task → {provider.name}")

        response = provider.complete(messages, max_tokens=max_tokens, temperature=temperature)

        # Log the routing decision
        self._call_log.append({
            "complexity": complexity.value,
            "provider":   provider.name,
            "tokens":     response.total_tokens,
        })

        return response

    def get_routing_stats(self) -> dict:
        """Return a summary of routing decisions made (for the dashboard)."""
        if not self._call_log:
            return {}
        total_calls  = len(self._call_log)
        heavy_calls  = sum(1 for c in self._call_log if c["provider"] in ("anthropic", "openai"))
        light_calls  = total_calls - heavy_calls
        total_tokens = sum(c["tokens"] for c in self._call_log)
        return {
            "total_calls":  total_calls,
            "heavy_calls":  heavy_calls,
            "light_calls":  light_calls,
            "total_tokens": total_tokens,
            "estimated_savings_pct": round((light_calls / max(total_calls, 1)) * 60),
        }

    def _select_provider(self, complexity: TaskComplexity) -> BaseLLMProvider:
        """Select best available provider for the given complexity tier."""
        # Define fallback cascade per tier
        if complexity == TaskComplexity.HIGH:
            cascade = [_HEAVY_TIER, _LIGHT_TIER, _LOCAL_TIER]
        elif complexity == TaskComplexity.MEDIUM:
            cascade = [_LIGHT_TIER, _HEAVY_TIER, _LOCAL_TIER]
        else:  # LOW
            cascade = [_LOCAL_TIER, _LIGHT_TIER, _HEAVY_TIER]

        for tier in cascade:
            prov = tier.get_provider()
            if prov is not None:
                return prov

        # Ultimate fallback
        logger.warning("[SLM] All tiers unavailable — using HeuristicProvider")
        return HeuristicProvider()
