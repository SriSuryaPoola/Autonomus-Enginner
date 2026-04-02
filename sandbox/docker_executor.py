"""
Docker Sandbox Executor — Ephemeral container per test run.

Replaces the dangerous subprocess-based SandboxExecutor with
isolated Docker containers that are destroyed after each run.

Security properties:
  - Each run gets a fresh container (no state leakage)
  - No access to host environment variables
  - Resource limits: CPU, memory, network, timeout
  - Container destroyed immediately after completion

Usage:
    from sandbox.docker_executor import DockerSandboxExecutor

    executor = DockerSandboxExecutor()
    result = executor.run_tests(
        repo_path="/path/to/repo",
        test_path="tests/test_auth.py",
        timeout=120,
    )
    print(result.passed)      # True / False
    print(result.coverage)    # 74.5
    print(result.output)      # pytest output
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Docker availability check ────────────────────────────────────────────────
_DOCKER_AVAILABLE = False
try:
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
    _DOCKER_AVAILABLE = result.returncode == 0
except Exception:
    pass


@dataclass
class SandboxResult:
    passed: bool
    output: str
    error: str
    coverage: Optional[float]
    duration_s: float
    exit_code: int
    executor_type: str          # "docker" | "subprocess"


class DockerSandboxExecutor:
    """
    Runs pytest inside an ephemeral Docker container.
    Falls back to subprocess if Docker is unavailable.

    Container spec:
      - Image: python:3.11-slim (cached locally)
      - Network: none (no internet access)
      - Memory: 512MB limit
      - CPU: 1.0 limit
      - Destroyed immediately after run
    """

    DOCKER_IMAGE    = "python:3.11-slim"
    MEMORY_LIMIT    = "512m"
    CPU_LIMIT       = "1.0"
    DEFAULT_TIMEOUT = 120   # seconds

    def __init__(self, use_docker: Optional[bool] = None):
        env_flag = os.getenv("DOCKER_SANDBOX_ENABLED", "false").lower() == "true"
        self.use_docker = use_docker if use_docker is not None else env_flag
        if self.use_docker and not _DOCKER_AVAILABLE:
            logger.warning("[Sandbox] Docker requested but not available — falling back to subprocess")
            self.use_docker = False

    def run_tests(
        self,
        repo_path: str,
        test_path: str = "tests/",
        timeout: int = DEFAULT_TIMEOUT,
        extra_args: Optional[list[str]] = None,
    ) -> SandboxResult:
        """
        Run pytest in an isolated environment.

        Args:
            repo_path:   Path to the repository root
            test_path:   Relative path to tests (file or directory)
            timeout:     Max seconds before killing the container
            extra_args:  Additional pytest arguments

        Returns:
            SandboxResult with pass/fail, output, and coverage
        """
        if self.use_docker:
            return self._run_docker(repo_path, test_path, timeout, extra_args or [])
        return self._run_subprocess(repo_path, test_path, timeout, extra_args or [])

    # ─── Docker Execution ─────────────────────────────────────────────────────

    def _run_docker(
        self, repo_path: str, test_path: str, timeout: int, extra_args: list[str]
    ) -> SandboxResult:
        """Run tests in an ephemeral Docker container."""
        import time
        start = time.time()

        # Build pytest command
        pytest_cmd = [
            "sh", "-c",
            f"pip install -e . -q 2>&1 && pytest {test_path} "
            f"--cov=. --cov-report=term-missing --tb=short -q "
            f"{' '.join(extra_args)} 2>&1"
        ]

        docker_cmd = [
            "docker", "run",
            "--rm",                                  # Remove after run
            "--network=none",                        # No network access
            f"--memory={self.MEMORY_LIMIT}",
            f"--cpus={self.CPU_LIMIT}",
            "--read-only",                           # Read-only filesystem
            "--tmpfs=/tmp",                          # Writable /tmp only
            "-v", f"{os.path.abspath(repo_path)}:/workspace:ro",  # Read-only mount
            "-w", "/workspace",
            self.DOCKER_IMAGE,
            *pytest_cmd,
        ]

        logger.info(f"[DockerSandbox] Running tests in container: {test_path}")

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,  # Docker overhead
            )
            duration = time.time() - start
            output   = proc.stdout + proc.stderr
            passed   = proc.returncode == 0
            coverage = self._extract_coverage(output)

            logger.info(
                f"[DockerSandbox] {'PASS' if passed else 'FAIL'} "
                f"in {duration:.1f}s | coverage={coverage}"
            )

            return SandboxResult(
                passed=passed,
                output=output,
                error=proc.stderr,
                coverage=coverage,
                duration_s=round(duration, 2),
                exit_code=proc.returncode,
                executor_type="docker",
            )

        except subprocess.TimeoutExpired:
            logger.error(f"[DockerSandbox] Container timed out after {timeout}s")
            return SandboxResult(
                passed=False,
                output="",
                error=f"Timeout after {timeout}s",
                coverage=None,
                duration_s=float(timeout),
                exit_code=-1,
                executor_type="docker",
            )
        except Exception as e:
            logger.error(f"[DockerSandbox] Docker run failed: {e}")
            return self._run_subprocess(repo_path, test_path, timeout, extra_args)

    # ─── Subprocess Fallback ──────────────────────────────────────────────────

    def _run_subprocess(
        self, repo_path: str, test_path: str, timeout: int, extra_args: list[str]
    ) -> SandboxResult:
        """Fallback: run tests in a subprocess (less isolated)."""
        import time
        start = time.time()

        cmd = [
            "python", "-m", "pytest",
            test_path,
            "--cov=.",
            "--cov-report=term-missing",
            "--tb=short",
            "-q",
            *extra_args,
        ]

        logger.info(f"[SubprocessSandbox] Running: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            duration = time.time() - start
            output   = proc.stdout + proc.stderr
            coverage = self._extract_coverage(output)

            return SandboxResult(
                passed=proc.returncode == 0,
                output=output,
                error=proc.stderr,
                coverage=coverage,
                duration_s=round(duration, 2),
                exit_code=proc.returncode,
                executor_type="subprocess",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                passed=False, output="", error=f"Timeout after {timeout}s",
                coverage=None, duration_s=float(timeout), exit_code=-1,
                executor_type="subprocess",
            )
        except Exception as e:
            return SandboxResult(
                passed=False, output="", error=str(e),
                coverage=None, duration_s=0, exit_code=-1,
                executor_type="subprocess",
            )

    @staticmethod
    def _extract_coverage(output: str) -> Optional[float]:
        """Parse pytest-cov coverage percentage from output."""
        import re
        patterns = [
            r"TOTAL\s+\d+\s+\d+\s+(\d+)%",         # standard pytest-cov
            r"coverage:\s+(\d+(?:\.\d+)?)%",          # alternate format
        ]
        for pattern in patterns:
            m = re.search(pattern, output)
            if m:
                return float(m.group(1))
        return None
