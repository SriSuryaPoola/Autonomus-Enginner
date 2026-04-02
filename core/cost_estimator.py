"""
Cost Estimator — Pre-task token cost projection + budget gate.

Estimates the token cost of a task BEFORE execution starts.
If the estimate exceeds the user's budget threshold, the agent
pauses and requires explicit approval.

Usage:
    from core.cost_estimator import CostEstimator

    estimator = CostEstimator()
    estimate = estimator.estimate(
        task_description="Refactor auth module for JWT support",
        repo_path="/path/to/repo",
        provider="anthropic",
    )
    print(estimate.tokens)        # 32000
    print(estimate.cost_usd)      # "$0.096"
    print(estimate.requires_approval)  # False (below $5 budget)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Pricing Table (USD per 1M tokens) ───────────────────────────────────────
# Updated April 2026 estimates
PRICING_TABLE: dict[str, dict[str, float]] = {
    "anthropic": {"input": 3.00,  "output": 15.00},   # Claude 3.5 Sonnet
    "openai":    {"input": 2.50,  "output": 10.00},   # GPT-4o
    "gemini":    {"input": 1.25,  "output": 5.00},    # Gemini 1.5 Pro
    "ollama":    {"input": 0.00,  "output": 0.00},    # Local — free
    "heuristic": {"input": 0.00,  "output": 0.00},    # No LLM
}

# Tokens per phase (rough estimates based on empirical testing)
PHASE_TOKEN_ESTIMATES = {
    "understand":  1_500,
    "decompose":   2_000,
    "execute":     8_000,
    "validate":    3_000,
    "refine":      5_000,
    "patch":       6_000,
}

# Budget thresholds
DEFAULT_TASK_BUDGET   = 50_000   # tokens
DEFAULT_PROJECT_BUDGET = 500_000
APPROVAL_THRESHOLD_USD = 1.00    # Require approval above this cost


@dataclass
class CostEstimate:
    task_description: str
    provider: str
    estimated_tokens: int
    estimated_cost_usd: float
    budget_tokens: int
    budget_remaining_tokens: int
    requires_approval: bool
    breakdown: dict[str, int]   # phase → token estimate

    @property
    def cost_label(self) -> str:
        if self.estimated_cost_usd == 0:
            return "FREE (local model)"
        return f"~${self.estimated_cost_usd:.3f}"

    @property
    def summary(self) -> str:
        approval = " [APPROVAL REQUIRED]" if self.requires_approval else ""
        return (f"Estimated: {self.estimated_tokens:,} tokens | "
                f"{self.cost_label} | Provider: {self.provider}{approval}")


class CostEstimator:
    """
    Estimates task token cost before execution.
    Accounts for repo size, task complexity, and provider pricing.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        task_budget: int = DEFAULT_TASK_BUDGET,
        approval_threshold_usd: float = APPROVAL_THRESHOLD_USD,
    ):
        self.provider  = provider or os.getenv("LLM_PROVIDER", "heuristic")
        self.task_budget = task_budget
        self.approval_threshold = approval_threshold_usd
        self._spent_tokens: dict[str, int] = {}   # project_id → tokens used

    def estimate(
        self,
        task_description: str,
        repo_path: Optional[str] = None,
        project_id: str = "default",
        complexity_hint: Optional[str] = None,  # "low" | "medium" | "high"
        max_iterations: int = 5,
    ) -> CostEstimate:
        """
        Estimate token cost for a task before starting.

        Args:
            task_description: The task prompt
            repo_path:        Path to the repository (for size estimation)
            project_id:       For tracking cumulative spend
            complexity_hint:  Override complexity classification
            max_iterations:   Number of convergence loops expected
        """
        # Complexity classification
        if complexity_hint is None:
            complexity_hint = self._classify_complexity(task_description)

        # Repo size multiplier
        repo_multiplier = self._repo_size_multiplier(repo_path)

        # Complexity multiplier
        complexity_mult = {"low": 0.6, "medium": 1.0, "high": 1.8}.get(
            complexity_hint, 1.0
        )

        # Per-phase estimate
        breakdown: dict[str, int] = {}
        for phase, base_tokens in PHASE_TOKEN_ESTIMATES.items():
            adjusted = int(base_tokens * complexity_mult * repo_multiplier)
            breakdown[phase] = adjusted

        # Total: one full loop × iterations + overhead
        single_loop = sum(breakdown.values())
        total_tokens = int(single_loop * min(max_iterations, 3) * 0.7)  # diminishing per loop
        total_tokens = min(total_tokens, self.task_budget)

        # Cost calculation
        pricing = PRICING_TABLE.get(self.provider.lower(), PRICING_TABLE["heuristic"])
        input_ratio  = 0.65   # ~65% of tokens are input
        output_ratio = 0.35
        cost_usd = (
            (total_tokens * input_ratio  / 1_000_000 * pricing["input"]) +
            (total_tokens * output_ratio / 1_000_000 * pricing["output"])
        )

        # Budget tracking
        spent       = self._spent_tokens.get(project_id, 0)
        remaining   = max(0, self.task_budget - spent)
        requires_ap = cost_usd >= self.approval_threshold

        estimate = CostEstimate(
            task_description=task_description,
            provider=self.provider,
            estimated_tokens=total_tokens,
            estimated_cost_usd=round(cost_usd, 4),
            budget_tokens=self.task_budget,
            budget_remaining_tokens=remaining,
            requires_approval=requires_ap,
            breakdown=breakdown,
        )

        logger.info(f"[CostEstimator] {estimate.summary}")
        return estimate

    def record_spend(self, project_id: str, tokens_used: int) -> None:
        """Record actual token spend after task completion."""
        self._spent_tokens[project_id] = (
            self._spent_tokens.get(project_id, 0) + tokens_used
        )

    def get_project_spend(self, project_id: str) -> dict:
        spent = self._spent_tokens.get(project_id, 0)
        pricing = PRICING_TABLE.get(self.provider.lower(), PRICING_TABLE["heuristic"])
        cost = spent / 1_000_000 * (pricing["input"] * 0.65 + pricing["output"] * 0.35)
        return {
            "project_id": project_id,
            "tokens_used": spent,
            "estimated_cost_usd": round(cost, 4),
            "budget_tokens": DEFAULT_PROJECT_BUDGET,
            "budget_pct_used": round(spent / DEFAULT_PROJECT_BUDGET * 100, 1),
        }

    def _classify_complexity(self, task: str) -> str:
        task_lower = task.lower()
        high_words = {"refactor", "rewrite", "architect", "security", "auth", "migrate",
                      "redesign", "performance", "concurrency", "async"}
        low_words  = {"docstring", "comment", "rename", "format", "stub", "type hint",
                      "add import", "simple", "boilerplate"}
        if any(w in task_lower for w in high_words):
            return "high"
        if any(w in task_lower for w in low_words):
            return "low"
        return "medium"

    def _repo_size_multiplier(self, repo_path: Optional[str]) -> float:
        """Scale token estimates based on repository size."""
        if not repo_path or not os.path.isdir(repo_path):
            return 1.0
        try:
            py_files = list(Path(repo_path).rglob("*.py"))
            count = len(py_files)
            if count < 20:   return 0.7
            if count < 100:  return 1.0
            if count < 500:  return 1.4
            return 1.8   # Large monorepo
        except Exception:
            return 1.0
