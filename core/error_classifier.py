"""
Error Classification Taxonomy — Categorize failures before patching.

Replacing vague "test failed" with structured error types allows the
PatchEngine to apply the most effective repair strategy for each case.

Error Types:
  TEST_ISSUE       — The test logic is wrong (wrong assertion / import)
  CODE_BUG         — The implementation has a real bug (test is correct)
  ENV_ERROR        — Missing dependency, path error, fixture setup
  TOPOLOGY_ERROR   — Import cycle, missing module, wrong project structure
  TIMEOUT          — Test exceeded time limit
  LLM_HALLUCINATION — LLM generated syntactically invalid or nonsensical code
  COVERAGE_GAP     — Code path not covered by any test
  SECURITY_BLOCK   — Bandit/ruff blocked convergence (not a runtime failure)

Usage:
    from core.error_classifier import ErrorClassifier, ErrorType

    clf = ErrorClassifier()
    result = clf.classify(error_output="ImportError: No module named 'requests'")
    print(result.error_type)   # ErrorType.ENV_ERROR
    print(result.confidence)   # 0.92
    print(result.advice)       # "Add 'requests' to project dependencies..."
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    TEST_ISSUE       = "test_issue"
    CODE_BUG         = "code_bug"
    ENV_ERROR        = "env_error"
    TOPOLOGY_ERROR   = "topology_error"
    TIMEOUT          = "timeout"
    LLM_HALLUCINATION = "llm_hallucination"
    COVERAGE_GAP     = "coverage_gap"
    SECURITY_BLOCK   = "security_block"
    UNKNOWN          = "unknown"


@dataclass
class ClassificationResult:
    error_type: ErrorType
    confidence: float          # 0.0–1.0
    matched_pattern: str
    advice: str
    is_retryable: bool         # Can the agent retry without human input?


# ─── Pattern Rules ────────────────────────────────────────────────────────────
# Each rule: (pattern, ErrorType, confidence, advice, is_retryable)

_RULES: list[tuple[str, ErrorType, float, str, bool]] = [
    # LLM Hallucination — syntactically broken code
    (r"SyntaxError|IndentationError|TabError|unexpected EOF",
     ErrorType.LLM_HALLUCINATION, 0.95,
     "LLM generated invalid Python syntax. Retry with stricter prompt.", True),

    # Environment errors
    (r"ModuleNotFoundError|No module named|ImportError",
     ErrorType.ENV_ERROR, 0.90,
     "Missing dependency. Check pyproject.toml or install the module.", True),
    (r"FileNotFoundError|No such file or directory",
     ErrorType.ENV_ERROR, 0.88,
     "File path error. Check working directory or fixture setup.", True),
    (r"PermissionError|AccessDenied",
     ErrorType.ENV_ERROR, 0.85,
     "Permission denied. Check file system permissions.", False),

    # Timeout
    (r"TimeoutError|timed out|Timeout|TIMEOUT",
     ErrorType.TIMEOUT, 0.92,
     "Test exceeded time limit. Check for infinite loops or slow I/O.", False),

    # Topology / structural errors
    (r"circular import|ImportCycle|cannot import name",
     ErrorType.TOPOLOGY_ERROR, 0.88,
     "Circular import detected. Refactor module dependencies.", False),
    (r"AttributeError: module|has no attribute",
     ErrorType.TOPOLOGY_ERROR, 0.75,
     "Module attribute missing. Check import path and module structure.", True),

    # Security gate blocks
    (r"bandit|security.*FAIL|HIGH severity|MEDIUM severity",
     ErrorType.SECURITY_BLOCK, 0.90,
     "Bandit security check failed. Review flagged code before proceeding.", False),
    (r"ruff.*FAIL|lint.*error",
     ErrorType.SECURITY_BLOCK, 0.80,
     "Ruff linting failed. Run 'ruff check --fix' to auto-repair.", True),

    # Test logic errors (assertion failures)
    (r"AssertionError|assert.*==.*!=|Expected.*but got",
     ErrorType.TEST_ISSUE, 0.82,
     "Assertion failed. The test expectations may need updating.", True),
    (r"pytest\.raises|Expected exception|did not raise",
     ErrorType.TEST_ISSUE, 0.80,
     "Exception expectation failed. Check test logic.", True),

    # Coverage gaps
    (r"coverage.*below|--cov-fail-under|FAIL Required test coverage",
     ErrorType.COVERAGE_GAP, 0.95,
     "Coverage threshold not met. Add tests for uncovered branches.", True),

    # Code bugs (implementation errors caught by tests)
    (r"TypeError|ValueError|KeyError|IndexError|ZeroDivisionError",
     ErrorType.CODE_BUG, 0.78,
     "Runtime error in implementation. Patch the source code, not the test.", True),
    (r"RecursionError|OverflowError",
     ErrorType.CODE_BUG, 0.85,
     "Recursion or overflow error in implementation logic.", True),
    (r"NotImplementedError",
     ErrorType.CODE_BUG, 0.90,
     "Stub not implemented. The agent must implement the missing method.", True),
]

_COMPILED_RULES = [(re.compile(pattern, re.IGNORECASE), etype, conf, advice, retryable)
                   for pattern, etype, conf, advice, retryable in _RULES]


# ─── Classifier ───────────────────────────────────────────────────────────────

class ErrorClassifier:
    """
    Classifies test failure output into a structured ErrorType.
    Used by PatchEngine to select the optimal repair strategy.
    """

    def classify(
        self,
        error_output: str,
        test_code: Optional[str] = None,
        impl_code: Optional[str] = None,
    ) -> ClassificationResult:
        """
        Classify the error from pytest/subprocess output.

        Args:
            error_output: Full stderr/stdout from failed test run
            test_code:    The test file content (optional, improves accuracy)
            impl_code:    The implementation file content (optional)

        Returns:
            ClassificationResult with error type, confidence, and advice
        """
        best: Optional[ClassificationResult] = None

        for pattern, etype, conf, advice, retryable in _COMPILED_RULES:
            if pattern.search(error_output):
                result = ClassificationResult(
                    error_type=etype,
                    confidence=conf,
                    matched_pattern=pattern.pattern,
                    advice=advice,
                    is_retryable=retryable,
                )
                if best is None or conf > best.confidence:
                    best = result

        if best is not None:
            return best

        return ClassificationResult(
            error_type=ErrorType.UNKNOWN,
            confidence=0.3,
            matched_pattern="",
            advice="Unknown error type. Review output manually.",
            is_retryable=True,
        )

    def classify_batch(self, errors: list[str]) -> list[ClassificationResult]:
        """Classify multiple error outputs at once."""
        return [self.classify(e) for e in errors]

    def is_agent_fixable(self, result: ClassificationResult) -> bool:
        """
        Returns True if the agent should attempt to auto-fix,
        False if human intervention is required.
        """
        non_fixable = {ErrorType.TIMEOUT, ErrorType.SECURITY_BLOCK,
                       ErrorType.TOPOLOGY_ERROR, ErrorType.UNKNOWN}
        return result.error_type not in non_fixable and result.is_retryable

    def repair_strategy(self, result: ClassificationResult) -> str:
        """Return the recommended patch target: 'test' | 'implementation' | 'deps' | 'escalate'"""
        strategy_map = {
            ErrorType.TEST_ISSUE:        "test",
            ErrorType.CODE_BUG:          "implementation",
            ErrorType.ENV_ERROR:         "deps",
            ErrorType.TOPOLOGY_ERROR:    "escalate",
            ErrorType.TIMEOUT:           "escalate",
            ErrorType.LLM_HALLUCINATION: "implementation",
            ErrorType.COVERAGE_GAP:      "test",
            ErrorType.SECURITY_BLOCK:    "escalate",
            ErrorType.UNKNOWN:           "escalate",
        }
        return strategy_map.get(result.error_type, "escalate")
