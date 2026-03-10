"""All-in-one starter for the onTro-Finance operations console."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


def _resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()


def _app_home() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else _resource_root()


def _prepare_runtime_environment() -> None:
    app_home = _app_home()
    resource_root = _resource_root()

    os.environ.setdefault("ONTRO_APP_HOME", str(app_home))
    os.environ.setdefault("ONTRO_STORAGE_BACKEND", "inmemory")

    console_dist = resource_root / "frontend" / "dist"
    if console_dist.exists():
        os.environ.setdefault("ONTRO_CONSOLE_DIST_DIR", str(console_dist))

    for relative_path in ("data", "data/domain", "data/raw", "data/personal", "data/learning"):
        (app_home / relative_path).mkdir(parents=True, exist_ok=True)


def _wait_for_port(host: str, port: int, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _open_browser_when_ready(host: str, port: int) -> None:
    if _wait_for_port(host, port):
        webbrowser.open(f"http://{host}:{port}/")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the onTro-Finance operations console as a single local web application.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for the local web server.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for the local web server.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the local server without opening the browser automatically.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _prepare_runtime_environment()
    from main import app

    if not args.no_browser:
        threading.Thread(
            target=_open_browser_when_ready,
            args=(args.host, args.port),
            daemon=True,
        ).start()

    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
