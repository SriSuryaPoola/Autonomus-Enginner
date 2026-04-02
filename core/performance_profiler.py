"""
Performance Profiler — P3 Original Feature.

Tracks latency, token efficiency, and error rate per agent step.
Enables the platform to identify bottlenecks and optimize routing.

Produces:
  - Per-step timing (ms)
  - Token efficiency ratio (output quality / tokens used)
  - Error frequency per phase
  - Slowest steps + optimization suggestions
  - JSON-serializable reports for the Dashboard

Usage:
    from core.performance_profiler import PerformanceProfiler

    profiler = PerformanceProfiler()

    with profiler.step("execute", agent="developer"):
        # ... run the step ...
        pass

    report = profiler.report()
    print(report["slowest_step"])     # "execute"
    print(report["total_duration_s"]) # 12.4
"""

from __future__ import annotations

import time
import logging
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    step_name: str
    agent: str
    duration_ms: float
    tokens_used: int
    success: bool
    error_type: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def tokens_per_second(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.tokens_used / (self.duration_ms / 1000)


class PerformanceProfiler:
    """
    Lightweight per-session performance profiler for the agent pipeline.
    Tracks every step, computes summary statistics, and surfaces
    optimization hints for the dashboard.
    """

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self._records: list[StepRecord] = []
        self._step_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._session_start = time.time()

    @contextmanager
    def step(
        self,
        step_name: str,
        agent: str = "unknown",
        tokens_used: int = 0,
    ) -> Iterator[None]:
        """
        Context manager to time a step.

        Usage:
            with profiler.step("execute", agent="developer", tokens_used=3000):
                run_code()
        """
        start = time.time()
        success = True
        error_type = None
        try:
            yield
        except Exception as exc:
            success = False
            error_type = type(exc).__name__
            logger.warning(f"[Profiler] Step '{step_name}' failed: {exc}")
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            record = StepRecord(
                step_name=step_name,
                agent=agent,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                success=success,
                error_type=error_type,
            )
            self._records.append(record)
            self._step_counts[step_name] += 1
            if not success:
                self._error_counts[step_name] += 1

            logger.debug(
                f"[Profiler] {step_name}/{agent}: {duration_ms:.0f}ms "
                f"| tokens={tokens_used} | {'OK' if success else 'FAIL'}"
            )

    def record(
        self,
        step_name: str,
        agent: str,
        duration_ms: float,
        tokens_used: int = 0,
        success: bool = True,
        error_type: Optional[str] = None,
    ) -> None:
        """Manually record a step (use when context manager isn't convenient)."""
        record = StepRecord(
            step_name=step_name,
            agent=agent,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            success=success,
            error_type=error_type,
        )
        self._records.append(record)
        self._step_counts[step_name] += 1
        if not success:
            self._error_counts[step_name] += 1

    def report(self) -> dict:
        """Generate a full performance report (JSON-serializable)."""
        if not self._records:
            return {"status": "no_data", "records": 0}

        total_duration_s = time.time() - self._session_start
        total_tokens     = sum(r.tokens_used for r in self._records)
        total_steps      = len(self._records)
        failed_steps     = sum(1 for r in self._records if not r.success)

        # Per-step averages
        step_stats: dict[str, dict] = {}
        for step in set(r.step_name for r in self._records):
            step_records = [r for r in self._records if r.step_name == step]
            durations    = [r.duration_ms for r in step_records]
            step_stats[step] = {
                "count":       len(step_records),
                "avg_ms":      round(sum(durations) / len(durations), 1),
                "max_ms":      round(max(durations), 1),
                "min_ms":      round(min(durations), 1),
                "error_rate":  round(self._error_counts[step] / len(step_records), 3),
                "total_tokens": sum(r.tokens_used for r in step_records),
            }

        # Slowest step
        slowest = max(step_stats, key=lambda s: step_stats[s]["avg_ms"])

        # Optimization hints
        hints = self._generate_hints(step_stats, total_tokens, total_duration_s)

        return {
            "project_id":       self.project_id,
            "total_duration_s": round(total_duration_s, 2),
            "total_steps":      total_steps,
            "failed_steps":     failed_steps,
            "success_rate":     round((total_steps - failed_steps) / max(total_steps, 1), 3),
            "total_tokens":     total_tokens,
            "tokens_per_step":  round(total_tokens / max(total_steps, 1)),
            "slowest_step":     slowest,
            "step_stats":       step_stats,
            "optimization_hints": hints,
        }

    def agent_health(self) -> list[dict]:
        """Return per-agent health metrics for the dashboard."""
        agents: dict[str, list[StepRecord]] = defaultdict(list)
        for r in self._records:
            agents[r.agent].append(r)

        return [
            {
                "agent":        agent,
                "total_steps":  len(records),
                "error_rate":   round(sum(1 for r in records if not r.success) / len(records), 3),
                "avg_latency_ms": round(sum(r.duration_ms for r in records) / len(records), 1),
                "total_tokens": sum(r.tokens_used for r in records),
                "status":       "healthy" if sum(1 for r in records if not r.success) / len(records) < 0.2 else "degraded",
            }
            for agent, records in agents.items()
        ]

    def _generate_hints(self, step_stats: dict, total_tokens: int, total_s: float) -> list[str]:
        hints = []
        for step, stats in step_stats.items():
            if stats["error_rate"] > 0.3:
                hints.append(f"High error rate on '{step}' ({stats['error_rate']:.0%}) — check prompts")
            if stats["avg_ms"] > 30_000:
                hints.append(f"'{step}' is slow ({stats['avg_ms']/1000:.1f}s avg) — consider SLM routing")
        if total_tokens > 40_000:
            hints.append("High token usage — enable SLM routing for low-complexity steps")
        if total_s > 300:
            hints.append("Total session > 5 min — consider parallel agent execution")
        return hints[:5]
