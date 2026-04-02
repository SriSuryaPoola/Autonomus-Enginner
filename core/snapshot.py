"""
Snapshot Manager — Atomic Rollback for Agentic File Mutations.

Before any autonomous code change, call `SnapshotManager.take()`.
If convergence fails after MAX_RETRIES, call `SnapshotManager.rollback()`
to restore the last known green state.

Usage:
    snapshot = SnapshotManager(workspace_dir)
    snapshot.take()       # Before mutations
    # ... agent runs ...
    if not converged:
        snapshot.rollback()
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# File extensions considered "source" (rollback only affects these)
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".md"}

# Directories to exclude from snapshots
EXCLUDED_DIRS = {
    "__pycache__", ".git", "venv", ".venv", "node_modules",
    "test_repos", ".pytest_cache", "htmlcov", ".mypy_cache"
}


class SnapshotManager:
    """
    Takes lightweight filesystem snapshots before agent mutations
    and supports atomic rollback to the last green state.
    """

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir).resolve()
        self._snapshot_dir: Path | None = None
        self._snapshot_time: datetime | None = None

    def take(self) -> str:
        """
        Snapshot all source files in workspace.
        Returns the snapshot directory path.
        """
        tmp = tempfile.mkdtemp(prefix="ae_snapshot_")
        snapshot_path = Path(tmp)

        file_count = 0
        for src_file in self._iter_source_files():
            relative = src_file.relative_to(self.workspace)
            dest = snapshot_path / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            file_count += 1

        self._snapshot_dir = snapshot_path
        self._snapshot_time = datetime.now()
        logger.info(
            f"[Snapshot] Took snapshot of {file_count} files "
            f"from {self.workspace} → {snapshot_path}"
        )
        return str(snapshot_path)

    def rollback(self) -> bool:
        """
        Restore workspace to the snapshotted state.
        Returns True if rollback succeeded, False otherwise.
        """
        if not self._snapshot_dir or not self._snapshot_dir.exists():
            logger.error("[Snapshot] No snapshot available — cannot rollback")
            return False

        restored = 0
        try:
            for snap_file in self._snapshot_dir.rglob("*"):
                if snap_file.is_file():
                    relative = snap_file.relative_to(self._snapshot_dir)
                    target = self.workspace / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snap_file, target)
                    restored += 1

            age = (datetime.now() - self._snapshot_time).total_seconds()
            logger.warning(
                f"[Snapshot] ⚠️  ROLLED BACK {restored} files "
                f"(snapshot was {age:.0f}s old) → {self.workspace}"
            )
            return True

        except Exception as e:
            logger.error(f"[Snapshot] Rollback failed: {e}")
            return False

    def cleanup(self):
        """Remove the temporary snapshot directory."""
        if self._snapshot_dir and self._snapshot_dir.exists():
            shutil.rmtree(self._snapshot_dir, ignore_errors=True)
            logger.debug(f"[Snapshot] Cleaned up {self._snapshot_dir}")
            self._snapshot_dir = None

    def _iter_source_files(self):
        """Yield source files, skipping excluded directories."""
        for root, dirs, files in os.walk(self.workspace):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix in SOURCE_EXTENSIONS:
                    yield fpath

    @property
    def has_snapshot(self) -> bool:
        return self._snapshot_dir is not None and self._snapshot_dir.exists()

    def __repr__(self) -> str:
        return (
            f"SnapshotManager(workspace={self.workspace}, "
            f"snapshot={'active' if self.has_snapshot else 'none'})"
        )
