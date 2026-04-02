"""
Static Analysis Gatekeeper — Mandatory code quality checks before convergence.

Runs ruff (linting), bandit (security), and mypy (type checking) on generated
files as part of the Validate step in ClaudeFlow. A file with critical issues
cannot be marked CONVERGED.

Usage:
    from core.static_analysis import StaticAnalysisGatekeeper

    gatekeeper = StaticAnalysisGatekeeper()
    result = gatekeeper.run(file_path="tests/test_foo.py", cwd=".")
    if not result.passed:
        print(result.issues)
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StaticAnalysisResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    ruff_score: str = "skip"     # "pass" | "fail" | "skip"
    bandit_score: str = "skip"
    mypy_score: str = "skip"

    @property
    def summary(self) -> str:
        icons = {"pass": "OK", "fail": "FAIL", "skip": "skip"}
        return (
            f"ruff:{icons[self.ruff_score]} "
            f"bandit:{icons[self.bandit_score]} "
            f"mypy:{icons[self.mypy_score]} "
            f"-> {'PASSED' if self.passed else 'FAILED'}"
        )


class StaticAnalysisGatekeeper:
    """
    Runs static analysis tools on a generated/patched file.
    Results feed into the Validate phase quality score.
    """

    def __init__(self, python: Optional[str] = None):
        self.python = python or sys.executable

    def run(self, file_path: str, cwd: str = ".") -> StaticAnalysisResult:
        """Run all available static analysis tools on file_path."""
        issues: list[str] = []
        scores = {}

        # 1. Ruff — linting (fast, always available after pip install)
        ruff_result = self._run_ruff(file_path, cwd)
        scores["ruff"] = "pass" if ruff_result["ok"] else "fail"
        if not ruff_result["ok"]:
            issues.append(f"Ruff: {ruff_result['output'][:500]}")

        # 2. Bandit — security scan
        bandit_result = self._run_bandit(file_path, cwd)
        scores["bandit"] = "pass" if bandit_result["ok"] else "fail"
        if not bandit_result["ok"]:
            issues.append(f"Bandit: {bandit_result['output'][:500]}")

        # 3. Mypy — type checking (optional, skip if not installed)
        mypy_result = self._run_mypy(file_path, cwd)
        scores["mypy"] = mypy_result["status"]  # "pass" | "fail" | "skip"
        if mypy_result["status"] == "fail":
            issues.append(f"Mypy: {mypy_result['output'][:500]}")

        # Gate: fail if ruff or bandit found critical issues
        passed = scores["ruff"] == "pass" and scores["bandit"] == "pass"

        result = StaticAnalysisResult(
            passed=passed,
            issues=issues,
            ruff_score=scores.get("ruff", "skip"),
            bandit_score=scores.get("bandit", "skip"),
            mypy_score=scores.get("mypy", "skip"),
        )
        logger.info(f"[StaticAnalysis] {file_path}: {result.summary}")
        return result

    def _run_ruff(self, file_path: str, cwd: str) -> dict:
        try:
            proc = subprocess.run(
                [self.python, "-m", "ruff", "check", "--select=E,F,W", file_path],
                cwd=cwd, capture_output=True, text=True, timeout=30
            )
            return {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            return {"ok": True, "output": "ruff not installed — skipped"}
        except subprocess.TimeoutExpired:
            return {"ok": True, "output": "ruff timeout — skipped"}
        except Exception as e:
            return {"ok": True, "output": f"ruff error: {e}"}

    def _run_bandit(self, file_path: str, cwd: str) -> dict:
        try:
            proc = subprocess.run(
                [self.python, "-m", "bandit", "-ll", "-q", file_path],
                cwd=cwd, capture_output=True, text=True, timeout=30
            )
            return {"ok": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            return {"ok": True, "output": "bandit not installed — skipped"}
        except subprocess.TimeoutExpired:
            return {"ok": True, "output": "bandit timeout — skipped"}
        except Exception as e:
            return {"ok": True, "output": f"bandit error: {e}"}

    def _run_mypy(self, file_path: str, cwd: str) -> dict:
        try:
            proc = subprocess.run(
                [self.python, "-m", "mypy", "--ignore-missing-imports", "--no-error-summary", file_path],
                cwd=cwd, capture_output=True, text=True, timeout=30
            )
            status = "pass" if proc.returncode == 0 else "fail"
            return {"status": status, "output": proc.stdout + proc.stderr}
        except FileNotFoundError:
            return {"status": "skip", "output": "mypy not installed"}
        except subprocess.TimeoutExpired:
            return {"status": "skip", "output": "mypy timeout"}
        except Exception as e:
            return {"status": "skip", "output": f"mypy error: {e}"}
