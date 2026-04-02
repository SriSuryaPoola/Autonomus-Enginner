"""
Autonomous Git Agent — P3 Original Feature.

Generates meaningful, structured commit messages from code diffs
and automatically stages + commits changes after successful convergence.

Commit format follows Conventional Commits spec:
  <type>(<scope>): <short description>

  <body>

  <footer>

Types: feat | fix | refactor | test | docs | chore | perf | security

Usage:
    from core.git_agent import GitAgent

    agent = GitAgent(repo_path="/path/to/repo")
    result = agent.commit_convergence(
        task_description="Add JWT authentication to user endpoints",
        files_changed=["core/auth.py", "tests/test_auth.py"],
        test_coverage=74.5,
        iterations=3,
    )
    print(result.commit_hash)    # "a3f9b2c"
    print(result.message)        # "feat(auth): add JWT authentication..."
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CommitResult:
    success: bool
    commit_hash: Optional[str]
    message: str
    files_committed: list[str]
    error: Optional[str] = None


# ─── Commit Type Classifier ───────────────────────────────────────────────────

_TYPE_KEYWORDS = {
    "feat":     ["add", "implement", "create", "introduce", "support", "new", "enable"],
    "fix":      ["fix", "bug", "patch", "repair", "resolve", "correct", "broken"],
    "refactor": ["refactor", "restructure", "clean", "simplify", "reorganize", "extract"],
    "test":     ["test", "spec", "coverage", "assert", "mock", "pytest"],
    "docs":     ["docs", "document", "readme", "comment", "docstring", "guide"],
    "perf":     ["optimize", "performance", "speed", "cache", "latency", "faster"],
    "security": ["security", "auth", "secret", "pii", "sanitize", "encrypt", "token"],
    "chore":    ["upgrade", "update", "bump", "dependency", "config", "settings"],
}


class GitAgent:
    """
    Autonomous git commit agent that generates meaningful commit messages
    and manages the git workflow after successful task convergence.
    """

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = repo_path or os.getcwd()

    def commit_convergence(
        self,
        task_description: str,
        files_changed: Optional[list[str]] = None,
        test_coverage: Optional[float] = None,
        iterations: int = 1,
        agent_id: str = "autonomous-engineer",
        dry_run: bool = False,
    ) -> CommitResult:
        """
        Stage all changed files and commit with a generated message.

        Args:
            task_description: The task that was completed
            files_changed:    Specific files to commit (None = all staged)
            test_coverage:    Final coverage % for commit message
            iterations:       How many loops it took to converge
            agent_id:         Agent identifier for the commit footer
            dry_run:          If True, generate message but don't actually commit
        """
        commit_type  = self._classify_type(task_description)
        scope        = self._extract_scope(task_description, files_changed)
        short_desc   = self._make_short_description(task_description, commit_type)
        body         = self._make_body(task_description, files_changed, test_coverage, iterations)
        footer       = self._make_footer(agent_id, iterations, test_coverage)

        message = f"{commit_type}({scope}): {short_desc}\n\n{body}\n\n{footer}"

        if dry_run:
            return CommitResult(
                success=True,
                commit_hash=None,
                message=message,
                files_committed=files_changed or [],
            )

        # Stage files
        try:
            if files_changed:
                for f in files_changed:
                    self._run_git(["add", f])
            else:
                self._run_git(["add", "-A"])

            # Commit
            self._run_git(["commit", "-m", message])

            # Get commit hash
            hash_result = self._run_git(["rev-parse", "--short", "HEAD"])
            commit_hash = hash_result.stdout.strip() if hash_result else None

            logger.info(f"[GitAgent] Committed: {commit_hash} — {commit_type}({scope}): {short_desc}")

            return CommitResult(
                success=True,
                commit_hash=commit_hash,
                message=message,
                files_committed=files_changed or [],
            )

        except Exception as e:
            logger.error(f"[GitAgent] Commit failed: {e}")
            return CommitResult(
                success=False,
                commit_hash=None,
                message=message,
                files_committed=[],
                error=str(e),
            )

    def get_diff_summary(self, files: Optional[list[str]] = None) -> str:
        """Get a brief summary of what changed (for message generation)."""
        try:
            cmd = ["diff", "--cached", "--stat"]
            if files:
                cmd.extend(["--", *files])
            result = self._run_git(cmd)
            return result.stdout.strip() if result else ""
        except Exception:
            return ""

    def has_uncommitted_changes(self) -> bool:
        """Return True if there are staged or unstaged changes."""
        try:
            result = self._run_git(["status", "--porcelain"])
            return bool(result and result.stdout.strip())
        except Exception:
            return False

    # ── Private helpers ───────────────────────────────────────────────────────

    def _classify_type(self, task: str) -> str:
        task_lower = task.lower()
        for commit_type, keywords in _TYPE_KEYWORDS.items():
            if any(kw in task_lower for kw in keywords):
                return commit_type
        return "feat"

    def _extract_scope(self, task: str, files: Optional[list[str]]) -> str:
        """Extract scope from changed file names or task keywords."""
        if files:
            # Use the most common directory as scope
            dirs = [Path(f).parts[0] if len(Path(f).parts) > 1 else Path(f).stem
                    for f in files]
            if dirs:
                from collections import Counter
                return Counter(dirs).most_common(1)[0][0]

        # Fallback: extract from task description
        scopes = {
            "auth": ["auth", "login", "jwt", "token", "session"],
            "api":  ["api", "endpoint", "route", "rest"],
            "core": ["core", "engine", "orchestrat"],
            "test": ["test", "coverage", "spec"],
            "ui":   ["ui", "dashboard", "frontend"],
            "db":   ["database", "model", "migration"],
            "ci":   ["ci", "pipeline", "workflow", "github actions"],
        }
        task_lower = task.lower()
        for scope, keywords in scopes.items():
            if any(k in task_lower for k in keywords):
                return scope
        return "general"

    def _make_short_description(self, task: str, commit_type: str) -> str:
        """Create a concise (<72 char) description from task."""
        # Remove common prefixes
        clean = re.sub(r'^(please\s+|can you\s+|implement\s+|add\s+)', '', task,
                       flags=re.IGNORECASE).strip()
        # Truncate to 72 chars
        if len(clean) > 65:
            clean = clean[:62] + "..."
        return clean[0].lower() + clean[1:] if clean else task[:65]

    def _make_body(
        self,
        task: str,
        files: Optional[list[str]],
        coverage: Optional[float],
        iterations: int,
    ) -> str:
        lines = [f"Task: {task}"]
        if files:
            lines.append(f"Files changed: {', '.join(files[:5])}"
                         + (" ..." if len(files or []) > 5 else ""))
        if coverage is not None:
            lines.append(f"Test coverage: {coverage:.1f}%")
        lines.append(f"Convergence iterations: {iterations}")
        return "\n".join(lines)

    def _make_footer(self, agent_id: str, iterations: int, coverage: Optional[float]) -> str:
        footer = [f"Generated-by: {agent_id}"]
        if coverage is not None:
            footer.append(f"Coverage: {coverage:.1f}%")
        footer.append(f"Iterations: {iterations}")
        return "\n".join(footer)

    def _run_git(self, args: list[str]) -> Optional[subprocess.CompletedProcess]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.error(f"[GitAgent] git {' '.join(args)} failed: {e}")
            return None
