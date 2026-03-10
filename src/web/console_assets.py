"""Helpers for serving the bundled operations console."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_console_dist_dir(project_root: Path) -> Path | None:
    override = os.getenv("ONTRO_CONSOLE_DIST_DIR")
    if override:
        candidate = Path(override).expanduser().resolve()
        return candidate if candidate.exists() else None

    candidate = (project_root / "frontend" / "dist").resolve()
    return candidate if candidate.exists() else None


def resolve_console_asset_path(request_path: str, project_root: Path) -> Path | None:
    dist_dir = resolve_console_dist_dir(project_root)
    if dist_dir is None:
        return None

    normalized = request_path.strip("/")
    index_path = dist_dir / "index.html"

    if not normalized:
        return index_path if index_path.exists() else None

    candidate = (dist_dir / normalized).resolve()
    if dist_dir not in candidate.parents and candidate != dist_dir:
        raise ValueError("Requested path resolves outside the console dist directory")

    if candidate.is_file():
        return candidate

    if normalized.startswith("assets/"):
        return None

    return index_path if index_path.exists() else None
