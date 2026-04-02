"""
Agent Reflector — Self-evaluation engine for Claude Flow sub-agents.

After each phase of the Claude Flow pipeline, the Reflector evaluates:
- Was this step successful?
- What issues were introduced?
- Should the plan be revised?
- What context should be passed forward?

This closes the "biggest gap" identified by all 3 AI agents:
modern agents evaluate themselves and improve mid-run.

Usage:
    from core.reflector import Reflector, ReflectionResult

    reflector = Reflector()
    result = reflector.evaluate(
        phase="execute",
        output="def add(a, b): return a - b",   # Bug: returns subtraction
        task_description="Add two numbers",
        previous_issues=["Missing type hints"],
    )
    print(result.passed)           # False
    print(result.issues)           # ["Logic error: subtraction instead of addition"]
    print(result.revised_plan)     # ["Fix the logic error in add()", "Add type hints"]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    """Output of a single Reflector evaluation."""
    phase: str
    passed: bool
    confidence: float              # 0.0–1.0 self-assessed confidence
    issues: list[str]              # Problems found in this step's output
    suggestions: list[str]         # Improvements for next iteration
    revised_plan: list[str]        # Reprioritized/modified task steps
    should_replan: bool            # True if major revision needed
    context_forward: dict          # Key context to pass to next phase

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"[Reflector/{self.phase}] {status} "
                f"confidence={self.confidence:.0%} "
                f"issues={len(self.issues)}")


# ─── Reflection Heuristics ───────────────────────────────────────────────────

# Patterns that suggest the output is low quality
_QUALITY_RED_FLAGS = [
    (r"TODO|FIXME|HACK|NotImplementedError",     "Unimplemented stubs detected"),
    (r"pass\s*$",                                 "Empty pass-through function body"),
    (r"def .+\(\):\s*\.\.\.",                     "Stub with ellipsis — not implemented"),
    (r"print\(.*debug|print\(.*test",             "Debug print statements in output"),
    (r"#\s*your code here",                       "Placeholder comment not replaced"),
    (r"import \*",                                "Wildcard import (bad practice)"),
    (r"except:\s*pass",                           "Bare except suppressing all errors"),
    (r"eval\(|exec\(",                            "Dangerous eval/exec usage"),
]

_COMPILED_FLAGS = [(re.compile(p, re.IGNORECASE | re.MULTILINE), msg)
                   for p, msg in _QUALITY_RED_FLAGS]


class Reflector:
    """
    Self-evaluation engine that checks phase outputs for quality issues
    and generates actionable improvement suggestions.

    Designed to be called after each Claude Flow sub-agent phase
    to enable mid-run course correction.
    """

    def evaluate(
        self,
        phase: str,
        output: str,
        task_description: str,
        previous_issues: Optional[list[str]] = None,
        iteration: int = 1,
        max_iterations: int = 5,
    ) -> ReflectionResult:
        """
        Evaluate the output of a Claude Flow phase.

        Args:
            phase:             Which phase produced this output
            output:            The code/text produced by the sub-agent
            task_description:  Original task to check relevance
            previous_issues:   Issues from previous iterations (detect loops)
            iteration:         Current iteration number
            max_iterations:    Total allowed iterations

        Returns:
            ReflectionResult with pass/fail, issues, and next steps
        """
        issues: list[str] = []
        suggestions: list[str] = []

        # ── Quality flag scan ──────────────────────────────────────────────
        for pattern, message in _COMPILED_FLAGS:
            if pattern.search(output):
                issues.append(message)

        # ── Length sanity checks ───────────────────────────────────────────
        if len(output.strip()) < 10:
            issues.append("Output is too short — likely incomplete or empty")
        if len(output) > 50_000:
            issues.append("Output is unusually large — possible context leak")

        # ── Repetition / loop detection ───────────────────────────────────
        if previous_issues:
            overlap = set(issues) & set(previous_issues)
            if len(overlap) >= 2:
                issues.append(f"LOOP DETECTED: same issues as previous iteration: {overlap}")
                suggestions.append("Change approach — current strategy is stuck in a loop")

        # ── Phase-specific checks ─────────────────────────────────────────
        phase_checks = self._phase_specific_checks(phase, output, task_description)
        issues.extend(phase_checks["issues"])
        suggestions.extend(phase_checks["suggestions"])

        # ── Confidence calculation ────────────────────────────────────────
        flags_found     = len(issues)
        base_confidence = max(0.4, 1.0 - (flags_found * 0.12))
        iter_penalty    = (iteration / max_iterations) * 0.1
        confidence      = max(0.1, base_confidence - iter_penalty)

        passed = flags_found == 0 and confidence >= 0.6

        # ── Plan revision ─────────────────────────────────────────────────
        revised_plan: list[str] = []
        should_replan = False
        if not passed:
            revised_plan = self._generate_revised_plan(issues, phase, task_description)
            should_replan = len(issues) >= 3 or "LOOP DETECTED" in " ".join(issues)

        result = ReflectionResult(
            phase=phase,
            passed=passed,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
            revised_plan=revised_plan,
            should_replan=should_replan,
            context_forward={
                "reflection_passed": passed,
                "confidence":        confidence,
                "issues_count":      len(issues),
                "phase":             phase,
            },
        )

        # Log the result
        if passed:
            logger.debug(result.summary)
        else:
            logger.warning(result.summary + f" | Issues: {issues[:3]}")

        return result

    def _phase_specific_checks(self, phase: str, output: str, task: str) -> dict:
        """Apply phase-specific quality rules."""
        issues: list[str] = []
        suggestions: list[str] = []

        if phase == "understand":
            if len(output.split()) < 20:
                issues.append("Understanding phase output too brief — task not decomposed")
            if "requirement" not in output.lower() and "goal" not in output.lower():
                suggestions.append("Explicitly state the requirements and success criteria")

        elif phase == "execute":
            if "def " not in output and "class " not in output and "import " not in output:
                issues.append("Execute phase did not produce Python code")
            if "return" not in output and "yield" not in output:
                suggestions.append("Ensure functions have return statements")

        elif phase == "validate":
            if "assert" not in output.lower() and "test" not in output.lower():
                suggestions.append("Validation should include assertions or test calls")

        elif phase == "refine":
            if output == "" or len(output) < 50:
                issues.append("Refinement phase produced no output")

        return {"issues": issues, "suggestions": suggestions}

    def _generate_revised_plan(
        self, issues: list[str], phase: str, task: str
    ) -> list[str]:
        """Generate a revised action plan based on detected issues."""
        plan = []
        for issue in issues:
            if "stub" in issue.lower() or "not implemented" in issue.lower():
                plan.append(f"Implement missing code bodies in {phase} output")
            elif "loop" in issue.lower():
                plan.append("Change patching strategy — current approach is stuck")
            elif "syntax" in issue.lower():
                plan.append("Fix syntax errors before proceeding to next phase")
            elif "import" in issue.lower():
                plan.append("Resolve import issues in generated code")
            else:
                plan.append(f"Address: {issue}")

        if not plan:
            plan.append(f"Re-attempt {phase} phase with additional context")

        return plan[:5]  # Cap at 5 action items
