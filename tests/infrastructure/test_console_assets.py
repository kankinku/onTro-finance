from pathlib import Path

import pytest

from src.web.console_assets import resolve_console_asset_path, resolve_console_dist_dir


def test_resolve_console_dist_dir_prefers_env_override(tmp_path, monkeypatch):
    dist_dir = tmp_path / "console-dist"
    dist_dir.mkdir()
    monkeypatch.setenv("ONTRO_CONSOLE_DIST_DIR", str(dist_dir))

    assert resolve_console_dist_dir(project_root=Path("C:/ignored")) == dist_dir


def test_resolve_console_asset_path_returns_asset_or_index(tmp_path, monkeypatch):
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    index_path = dist_dir / "index.html"
    asset_path = assets_dir / "app.js"
    index_path.write_text("<html>console</html>", encoding="utf-8")
    asset_path.write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("ONTRO_CONSOLE_DIST_DIR", str(dist_dir))

    assert resolve_console_asset_path("", project_root=Path("C:/ignored")) == index_path
    assert resolve_console_asset_path("assets/app.js", project_root=Path("C:/ignored")) == asset_path
    assert resolve_console_asset_path("graph/explorer", project_root=Path("C:/ignored")) == index_path


def test_resolve_console_asset_path_rejects_parent_traversal(tmp_path, monkeypatch):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html>console</html>", encoding="utf-8")
    monkeypatch.setenv("ONTRO_CONSOLE_DIST_DIR", str(dist_dir))

    with pytest.raises(ValueError, match="outside"):
        resolve_console_asset_path("../secret.txt", project_root=Path("C:/ignored"))
