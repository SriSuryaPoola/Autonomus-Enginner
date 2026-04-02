"""
HITL (Human-in-the-Loop) Break-Glass Manager.

Monitors agent confidence scores and pauses execution when confidence
drops below the configured threshold (default: 85%).

When triggered:
  - Broadcasts a HITL_REQUIRED event to the UI via the coordinator
  - Blocks the agent loop until human approval or rejection is received
  - The UI shows a break-glass modal requesting human review

Usage:
    from core.hitl_manager import HITLManager

    hitl = HITLManager(coordinator=hiclaw, project_id="abc123")
    decision = hitl.check(
        confidence=0.72,
        context="Refactoring auth.py — LLM uncertain about session handling",
        task_id="task_456"
    )
    if decision == "REJECTED":
        raise HITLRejectedError("Human rejected the agentic action")
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.85     # Below this → trigger HITL
HITL_TIMEOUT_SECONDS = 300      # Max wait before auto-reject (5 min)
AUTO_APPROVE_ABOVE   = 0.95     # Auto-approve if confidence is very high


class HITLDecision(str, Enum):
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"
    TIMEOUT   = "TIMEOUT"
    AUTO      = "AUTO"          # Approved automatically (high confidence)


class HITLRejectedError(Exception):
    """Raised when a human rejects an agentic action."""


# ─── HITL State ───────────────────────────────────────────────────────────────

class HITLRequest:
    """Represents a pending human review request."""

    def __init__(self, task_id: str, context: str, confidence: float):
        self.task_id    = task_id
        self.context    = context
        self.confidence = confidence
        self.created_at = time.time()
        self.decision: Optional[HITLDecision] = None

    def resolve(self, decision: HITLDecision) -> None:
        self.decision = decision

    @property
    def is_resolved(self) -> bool:
        return self.decision is not None

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


# ─── Manager ──────────────────────────────────────────────────────────────────

class HITLManager:
    """
    Monitors confidence scores and triggers human-in-the-loop pauses
    when an agent is uncertain about a complex or risky operation.
    """

    def __init__(
        self,
        coordinator=None,         # HiClaw coordinator for broadcasting events
        project_id: str = "",
        threshold: float = CONFIDENCE_THRESHOLD,
        timeout: float = HITL_TIMEOUT_SECONDS,
    ):
        self.coordinator = coordinator
        self.project_id  = project_id
        self.threshold   = threshold
        self.timeout     = timeout
        self._pending: dict[str, HITLRequest] = {}

    def check(
        self,
        confidence: float,
        context: str,
        task_id: str,
    ) -> HITLDecision:
        """
        Check confidence score and either:
        1. AUTO-APPROVE  — confidence > AUTO_APPROVE_ABOVE
        2. AUTO-PROCEED  — confidence >= threshold
        3. PAUSE         — confidence < threshold → wait for human

        Returns the HITLDecision for the caller to act on.
        """
        if confidence >= AUTO_APPROVE_ABOVE:
            logger.debug(f"[HITL] Auto-approved (confidence={confidence:.0%})")
            return HITLDecision.AUTO

        if confidence >= self.threshold:
            logger.debug(f"[HITL] Proceeding (confidence={confidence:.0%} >= {self.threshold:.0%})")
            return HITLDecision.AUTO

        # Below threshold — trigger break-glass
        logger.warning(
            f"[HITL] BREAK-GLASS triggered! "
            f"confidence={confidence:.0%} < {self.threshold:.0%}. Context: {context[:100]}"
        )
        request = HITLRequest(task_id=task_id, context=context, confidence=confidence)
        self._pending[task_id] = request

        # Broadcast to UI
        self._broadcast_hitl_event(request)

        # Poll for decision (blocking with timeout)
        return self._wait_for_decision(request)

    def resolve(self, task_id: str, decision: HITLDecision) -> None:
        """Called by the API endpoint when the human makes a decision."""
        if task_id in self._pending:
            self._pending[task_id].resolve(decision)
            logger.info(f"[HITL] Task {task_id} resolved: {decision}")

    def approve(self, task_id: str) -> None:
        self.resolve(task_id, HITLDecision.APPROVED)

    def reject(self, task_id: str) -> None:
        self.resolve(task_id, HITLDecision.REJECTED)

    def get_pending(self) -> list[dict]:
        """Return all pending HITL requests (for the API to serve to the UI)."""
        return [
            {
                "task_id":    r.task_id,
                "context":    r.context,
                "confidence": round(r.confidence * 100, 1),
                "age":        round(r.age_seconds),
            }
            for r in self._pending.values()
            if not r.is_resolved
        ]

    # ── Private ──────────────────────────────────────────────────────────────

    def _broadcast_hitl_event(self, request: HITLRequest) -> None:
        """Send HITL_REQUIRED event to the coordinator (→ UI via WebSocket)."""
        if not self.coordinator:
            return
        try:
            msg = {
                "type":       "HITL_REQUIRED",
                "task_id":    request.task_id,
                "confidence": round(request.confidence * 100, 1),
                "context":    request.context,
                "project_id": self.project_id,
            }
            # Use synchronous send if no event loop is running
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if loop:
                loop.create_task(self.coordinator.broadcast(msg))
            else:
                asyncio.run(self.coordinator.broadcast(msg))
        except Exception as e:
            logger.error(f"[HITL] Failed to broadcast HITL event: {e}")

    def _wait_for_decision(self, request: HITLRequest) -> HITLDecision:
        """Poll for a human decision with timeout."""
        poll_interval = 2.0  # seconds
        elapsed = 0.0

        while elapsed < self.timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            if request.is_resolved:
                decision = request.decision
                del self._pending[request.task_id]
                return decision

        # Timeout — auto-reject for safety
        logger.error(
            f"[HITL] Timed out after {self.timeout}s waiting for human decision "
            f"on task {request.task_id}. Auto-rejecting."
        )
        self._pending.pop(request.task_id, None)
        return HITLDecision.TIMEOUT


# ─── Confidence Calculator ───────────────────────────────────────────────────

def estimate_confidence(
    quality_score: float,
    iteration: int,
    max_iterations: int,
    coverage_pct: float,
    failure_count: int,
) -> float:
    """
    Heuristic confidence score (0.0–1.0) from multiple signals.
    Used to decide whether to trigger HITL.
    """
    # Base confidence from quality score
    conf = quality_score * 0.40

    # Coverage contribution (max 0.25)
    conf += min(coverage_pct / 100.0, 1.0) * 0.25

    # Iteration penalty — more iterations = less confident
    iter_ratio = 1.0 - (iteration / max(max_iterations, 1)) * 0.5
    conf += iter_ratio * 0.20

    # Failure penalty
    failure_penalty = min(failure_count * 0.05, 0.15)
    conf -= failure_penalty

    return max(0.0, min(1.0, conf))
