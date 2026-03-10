from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ops_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "ops" / "symphony"


def tasks_root(root: Path | None = None) -> Path:
    return ops_root(root) / "tasks"


def runs_root(root: Path | None = None) -> Path:
    return ops_root(root) / "runs"


def policies_root(root: Path | None = None) -> Path:
    return ops_root(root) / "policies"


def default_worktree_root(root: Path | None = None) -> Path:
    configured = os.getenv("ONTRO_SYMPHONY_WORKTREE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    repo_name = (root or project_root()).name
    return Path.home() / ".config" / "superpowers" / "worktrees" / repo_name
